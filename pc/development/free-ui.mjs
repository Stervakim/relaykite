#!/usr/bin/env node
/** Public browser UI only. No private endpoint requests or credential export. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';

const MAX_BYTES = 1_048_576;
const MAX_INPUT_BYTES = 8 * MAX_BYTES;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const fail = (status, reason, sent = false) => ({ status, reason, sent });

async function readRequest() {
  let size = 0;
  const chunks = [];
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_INPUT_BYTES) throw new Error('Input exceeds 8 MiB');
    chunks.push(chunk);
  }
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!request || typeof request !== 'object' || Array.isArray(request)) throw new Error('Expected an object');
  if (!['probe', 'generate'].includes(request.operation)) throw new Error('Unsupported operation');
  if (request.operation === 'generate' && (typeof request.prompt !== 'string' || !request.prompt.trim()
      || request.prompt.length > 120_000 || !/^[a-f0-9]{64}$/.test(request.fingerprint)
      || !/^ui_[A-Za-z0-9_-]{1,128}$/.test(request.request_id))) throw new Error('Invalid generation request');
  request.images ??= [];
  if (!Array.isArray(request.images) || request.images.length > 4) throw new Error('Invalid image attachments');
  for (const image of request.images) {
    if (!image || !['image/png', 'image/jpeg', 'image/webp'].includes(image.mime_type)
        || typeof image.data_base64 !== 'string' || image.data_base64.length > 2_796_208
        || !/^[A-Za-z0-9+/]*={0,2}$/.test(image.data_base64)) throw new Error('Invalid image attachment');
    const data = Buffer.from(image.data_base64, 'base64');
    const valid = image.mime_type === 'image/png' ? data.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
      : image.mime_type === 'image/jpeg' ? data[0] === 255 && data[1] === 216 && data[2] === 255
        : data.subarray(0, 4).toString() === 'RIFF' && data.subarray(8, 12).toString() === 'WEBP';
    if (!valid || data.length > 2 * MAX_BYTES || data.toString('base64') !== image.data_base64) throw new Error('Invalid image content');
  }
  return request;
}

async function visible(locator) {
  return await locator.first().isVisible().catch(() => false);
}

async function answerText(body) {
  const code = body.locator('pre code');
  // ChatGPT can wrap an otherwise valid JSON answer in a code block whose
  // language/copy controls are siblings of <code>. Never include those controls.
  if (await code.count() === 1 && await body.locator('p, li, blockquote, h1, h2, h3, h4').count() === 0) {
    return (await code.innerText()).trim();
  }
  return (await body.innerText()).trim();
}

async function attachImages(page, files) {
  let input = page.locator('input[type="file"]').first();
  if (await input.count() === 0) {
    const attach = page.getByRole('button', { name: /Add photos|Add files|Attach files|Upload files|Добавить фото|Добавить файлы|Прикрепить файлы/i }).first();
    if (!await visible(attach)) return false;
    await attach.click();
    input = page.locator('input[type="file"]').first();
    if (await input.count() === 0) {
      const upload = page.getByRole('menuitem', { name: /Upload from computer|Upload files|Загрузить с компьютера|Загрузить файлы/i }).first();
      if (!await visible(upload)) return false;
      const [chooser] = await Promise.all([page.waitForEvent('filechooser', { timeout: 8_000 }), upload.click()]);
      await chooser.setFiles(files);
    } else await input.setInputFiles(files);
  } else await input.setInputFiles(files);
  const deadline = Date.now() + 25_000;
  let stableSince = Date.now();
  while (Date.now() < deadline) {
    const ui = await observe(page);
    if (ui.quota || ui.challenge || ui.login) return false;
    const previews = page.locator('form img[src], [data-testid="composer"] img[src], [data-testid*="attachment"] img[src]');
    const busy = page.locator('[role="progressbar"], [aria-busy="true"]');
    const ready = await previews.count() >= files.length && !await visible(busy)
      && await visible(ui.send) && await ui.send.isEnabled();
    if (!ready) stableSince = Date.now();
    if (ready && Date.now() - stableSince >= 1_000) return true;
    await sleep(350);
  }
  return false;
}

async function observe(page) {
  // Locators are evaluated against the current DOM on every observation.
  const composer = page.locator('#prompt-textarea, textarea[data-testid="prompt-textarea"], [contenteditable="true"][data-lexical-editor="true"]').first();
  const send = page.locator('button[data-testid="send-button"]').or(page.getByRole('button', { name: /^(Send prompt|Send message|Send|Отправить сообщение|Отправить запрос|Отправить)$/i })).first();
  const stop = page.locator('button[data-testid="stop-button"]').or(page.getByRole('button', { name: /^(Stop generating|Stop streaming|Остановить генерацию|Остановить поток|Остановить)$/i })).first();
  const login = page.getByRole('button', { name: /^(Log in|Sign in|Войти)$/i }).or(page.getByRole('link', { name: /^(Log in|Sign in|Войти)$/i }));
  const account = page.locator('[data-testid="accounts-profile-button"]').or(page.getByRole('button', { name: /Open profile menu|Open account menu|Открыть меню профиля|Открыть меню аккаунта/i }));
  const notices = await page.locator('[role="alert"], [role="dialog"], [data-testid*="limit"], [data-testid*="toast"]').allInnerTexts().catch(() => []);
  const notice = notices.join('\n').slice(0, 12_000);
  const quota = /(?:you.ve reached|you have reached|usage limit|message limit|try again (?:after|later)|limit resets|достигнут.{0,35}лимит|вы исчерпали|лимит.{0,50}(?:исчерпан|достигнут)|повторите попытку позже)/i.test(notice);
  const challenge = /(?:verify you are human|checking your browser|подтвердите.{0,20}человек|проверка браузера|unusual activity|необычн.{0,20}активност)/i.test(notice)
    || /\/auth\//.test(page.url()) || await visible(page.locator('iframe[src*="challenges.cloudflare.com"]'));
  return { composer, send, stop, loggedIn: await visible(account), login: await visible(login), quota, challenge, stopping: await visible(stop) };
}

async function browserMain(options, request) {
  const profile = path.resolve(options.profile);
  const receipts = path.join(profile, '.relaykite-ui-receipts');
  let receiptPath;
  const conversationPath = request.operation === 'generate' && /^[a-f0-9]{32}$/.test(request.run_id || '')
    ? path.join(profile, '.relaykite-ui-chats', request.run_id + '.json') : null;
  let conversationUrl = 'https://chatgpt.com/';
  if (conversationPath) {
    try {
      const saved = JSON.parse(await fs.readFile(conversationPath, 'utf8'));
      const url = new URL(saved.url);
      if (url.origin !== 'https://chatgpt.com' || !/^\/c\/[a-zA-Z0-9-]+$/.test(url.pathname) || url.search || url.hash) throw new Error('Invalid saved conversation');
      conversationUrl = url.href;
    } catch (error) {
      if (error.code !== 'ENOENT') return fail('waiting_user', 'Saved ChatGPT conversation cannot be verified; inspect its local receipt.');
    }
  }
  if (request.operation === 'generate') {
    receiptPath = path.join(receipts, request.fingerprint + '.json');
    try {
      const previous = JSON.parse(await fs.readFile(receiptPath, 'utf8'));
      if (previous.state === 'completed' && typeof previous.text === 'string') return { status: 'completed', text: previous.text, sent: true, receipt: request.fingerprint };
      return fail('uncertain', 'Matching browser receipt is pending; inspect the browser. This request will not be resent.', true);
    } catch (error) {
      if (error.code !== 'ENOENT') return fail('uncertain', 'Browser receipt cannot be verified; automatic resend disabled.', true);
    }
  }
  let chromium;
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    return fail('waiting_user', 'Install the optional local browser dependency: npm --prefix pc/development install, then npm --prefix pc/development run install-browser');
  }
  await fs.mkdir(profile, { recursive: true });
  let context;
  let sent = false;
  try {
    let browserLocation = options.channel ? { channel: options.channel } : {};
    if (options.channel === 'brave') {
      const candidates = process.platform === 'win32' ? [
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
        path.join(process.env.LOCALAPPDATA || '', 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
      ] : process.platform === 'darwin' ? ['/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'] : ['/usr/bin/brave-browser', '/usr/bin/brave'];
      let executablePath;
      for (const candidate of candidates) {
        if (await fs.stat(candidate).then(value => value.isFile()).catch(() => false)) { executablePath = candidate; break; }
      }
      if (!executablePath) return fail('waiting_user', 'Brave browser is not installed in a supported local location.');
      browserLocation = { executablePath };
    }
    context = await chromium.launchPersistentContext(profile, {
      headless: options.headless === true,
      chromiumSandbox: true,
      acceptDownloads: false,
      viewport: { width: 1280, height: 900 },
      timeout: 20_000,
      ...browserLocation,
    });
    context.setDefaultTimeout(8_000);
    const page = await context.newPage();
    // A run uses an ordinary saved conversation; Codex supplies bounded history.
    await page.goto(conversationUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    if (request.operation === 'login') {
      process.stderr.write('Sign in manually in the dedicated RelayKite browser, then close that browser window. No credentials are read by RelayKite.\n');
      await new Promise(resolve => context.once('close', resolve));
      context = null;
      return { status: 'ready', reason: 'Manual browser session closed. Run a capability probe to verify authentication.', sent: false };
    }
    const readyDeadline = Date.now() + 12_000;
    let ui;
    while (Date.now() < readyDeadline) {
      ui = await observe(page);
      if (ui.quota || ui.challenge || ui.login || (ui.loggedIn && await visible(ui.composer))) break;
      await sleep(500);
    }
    if (ui?.quota) return fail('waiting_model', 'ChatGPT reports a usage limit. Wait for the account limit to reset.');
    if (ui?.challenge) return fail('waiting_user', 'Browser authentication or human verification is required. Run the driver with --login.');
    if (!ui?.loggedIn || ui.login) return fail('waiting_user', 'Sign in manually in the dedicated profile: node pc/development/free-ui.mjs --profile <profile> --login');
    if (!await visible(ui.composer)) return fail('waiting_user', 'ChatGPT composer is unavailable or the page layout has changed.');
    if (request.operation === 'probe') return { status: 'ready', reason: 'Authenticated browser and composer observed. Model quota and generation are not yet verified.', sent: false };

    const assistants = page.locator('[data-message-author-role="assistant"]');
    const users = page.locator('[data-message-author-role="user"]');
    const beforeAssistant = await assistants.count();
    const beforeUser = await users.count();
    await ui.composer.fill(request.prompt);
    if (request.images?.length) {
      const imageFiles = [];
      for (let index = 0; index < request.images.length; index++) {
        const image = request.images[index];
        const extension = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }[image.mime_type];
        // FilePayload uses the native browser upload path without leaving screenshots
        // in a temporary directory when the owning process is force-cancelled.
        imageFiles.push({ name: `image-${index + 1}.${extension}`, mimeType: image.mime_type, buffer: Buffer.from(image.data_base64, 'base64') });
      }
      if (!await attachImages(page, imageFiles)) return fail('waiting_user', 'Image upload or preview readiness could not be confirmed; no message was sent. Check quota or upload controls in the dedicated browser.');
    }
    ui = await observe(page);
    if (!await visible(ui.send) || !await ui.send.isEnabled()) return fail('waiting_user', 'Send control is missing or disabled; no message was sent.');
    // Persist the receipt before the first potentially irreversible UI send.
    await fs.mkdir(receipts, { recursive: true });
    const handle = await fs.open(receiptPath, 'wx');
    try {
      await handle.writeFile(JSON.stringify({ state: 'pending', request_id: request.request_id, at: new Date().toISOString() }));
      await handle.sync();
    } finally {
      await handle.close();
    }
    sent = true; // A failed click can still have delivered the message; never retry it.
    await ui.send.click();
    const deadline = Date.now() + 200_000;
    let previousText = '';
    let stableSince = Date.now();
    let sawGeneration = false;
    let sawUser = false;
    while (Date.now() < deadline) {
      await sleep(700);
      ui = await observe(page);
      if (ui.quota) return fail('waiting_model', 'ChatGPT reports a usage limit after send. Request receipt is retained; no automatic resend.', true);
      if (ui.challenge || ui.login) return fail('waiting_user', 'Authentication changed after send. Inspect the dedicated browser before recovery.', true);
      sawGeneration ||= ui.stopping;
      sawUser ||= await users.count() > beforeUser;
      if (await assistants.count() <= beforeAssistant) continue;
      const answer = assistants.last();
      // Markdown innerText preserves the actual JSON contents without UI action labels.
      const body = answer.locator('.markdown').last();
      if (!await visible(body)) continue;
      const text = await answerText(body);
      if (Buffer.byteLength(text, 'utf8') > MAX_BYTES) return fail('uncertain', 'Assistant response exceeds 1 MiB.', true);
      if (text !== previousText || ui.stopping) {
        previousText = text;
        stableSince = Date.now();
      }
      const doneActions = answer.locator('button[data-testid="copy-turn-action-button"]').or(answer.getByRole('button', { name: /^(Copy|Copy response|Скопировать|Копировать)$/i }));
      if (sawUser && text && !ui.stopping && Date.now() - stableSince >= 3_500
          && (sawGeneration || await visible(doneActions))) {
        // Require a fresh second observation immediately before accepting completion.
        const final = await observe(page);
        if (final.stopping || await answerText(body) !== text) continue;
        if (conversationPath) {
          const url = new URL(page.url());
          if (url.origin !== 'https://chatgpt.com' || !/^\/c\/[a-zA-Z0-9-]+$/.test(url.pathname)) {
            return fail('uncertain', 'Saved conversation URL was not confirmed; inspect the existing chat before continuing.', true);
          }
          await fs.mkdir(path.dirname(conversationPath), { recursive: true, mode: 0o700 });
          await fs.writeFile(conversationPath, JSON.stringify({ url: url.origin + url.pathname }), { mode: 0o600 });
        }
        const record = { state: 'completed', request_id: request.request_id, text, at: new Date().toISOString() };
        const temporary = receiptPath + '.' + process.pid + '.tmp';
        const completed = await fs.open(temporary, 'wx');
        try { await completed.writeFile(JSON.stringify(record)); await completed.sync(); }
        finally { await completed.close(); }
        await fs.rename(temporary, receiptPath);
        return { status: 'completed', text, sent: true, receipt: request.fingerprint };
      }
    }
    return fail('uncertain', 'No confirmed completed assistant answer before deadline. Inspect the browser receipt; do not resend.', true);
  } catch (error) {
    return fail(sent ? 'uncertain' : 'waiting_user', sent
      ? 'Browser operation failed after the send receipt. Inspect the dedicated session; no automatic resend.'
      : 'Cannot open or inspect the dedicated browser. Install Chromium, close another process using this profile, or authenticate with --login.', sent);
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

let result;
try {
  const { values } = parseArgs({ options: { profile: { type: 'string' }, channel: { type: 'string' }, headless: { type: 'boolean', default: false }, login: { type: 'boolean', default: false } }, strict: true });
  if (!values.profile || (values.login && values.headless)) throw new Error('A dedicated --profile is required; --login needs a visible browser');
  values.channel ??= process.env.RELAYKITE_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined);
  if (values.channel && !['chromium', 'chrome', 'msedge', 'brave'].includes(values.channel)) throw new Error('Unsupported browser channel');
  const request = values.login ? { operation: 'login' } : await readRequest();
  result = await browserMain(values, request);
} catch {
  result = fail('waiting_user', 'Invalid driver input. Supply --profile <dedicated path> and one valid JSON request on stdin, or --login.');
}
process.stdout.write(JSON.stringify(result) + '\n');
