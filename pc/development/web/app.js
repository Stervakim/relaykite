/* RelayKite local control room. No external dependencies or remote resources. */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);
  const storage = {
    get(key) { try { return sessionStorage.getItem(key) || ""; } catch { return ""; } },
    set(key, value) { try { sessionStorage.setItem(key, value); } catch { /* A private tab can deny storage. */ } },
  };
  const tokenKey = "relaykite.local.token";
  const fragment = new URLSearchParams(location.hash.slice(1));
  let token = fragment.get("token") || storage.get(tokenKey);
  if (fragment.has("token")) {
    storage.set(tokenKey, token);
    fragment.delete("token");
    history.replaceState(null, "", location.pathname + location.search + (fragment.size ? "#" + fragment : ""));
  }
  const state = { runs: [], run: null, events: [], artifacts: [], capabilities: null, generation: 0, refreshBusy: false, detailBusy: false, submitting: false, actionBusy: false, connected: false, context: null, retryRequest: null, stopped: false, operationError: "" };
  const terminalStates = new Set(["completed", "failed", "cancelled", "stopped"]);
  const statusNames = { queued: "В очереди", pending: "Ожидание", running: "Выполняется", paused: "На паузе", completed: "Завершено", failed: "Ошибка", cancelled: "Остановлено", stopped: "Остановлено", waiting_provider: "Ожидает ChatGPT", waiting_model: "Ожидает модель", waiting_approval: "Нужно решение", waiting_user: "Нужно действие", interrupted: "Прервано", recovering: "Восстановление", uncertain: "Нужна проверка" };
  const eventNames = { "run.created": "Задача создана", "run.started": "Выполнение началось", "run.completed": "Задача завершена", "run.failed": "Ошибка выполнения", "run.paused": "Задача приостановлена", "run.resumed": "Выполнение продолжено", "run.cancelled": "Задача остановлена", "tool.started": "Инструмент запущен", "tool.completed": "Инструмент завершил работу", "tool.failed": "Ошибка инструмента", "context.compacted": "Контекст сжат", "checkpoint.created": "Контрольная точка сохранена", "provider.waiting": "Ожидается подключение провайдера", "provider.requested": "Модели отправлен запрос", "verification.started": "Началась проверка результата", "verification.completed": "Проверка результата завершена" };
  const safeText = (value, max = 20000) => {
    if (value == null) return "";
    let valueText = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    if (token) valueText = valueText.split(token).join("[токен скрыт]");
    return valueText.length > max ? valueText.slice(0, max) + "\n… показан фрагмент" : valueText;
  };
  const text = (id, value) => { $(id).textContent = safeText(value); };
  const feedback = (id, message, kind = "error") => { text(id, message); $(id).hidden = !message; $(id).dataset.kind = kind; };
  const element = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value != null) node.textContent = safeText(value); return node; };
  const asDate = (value) => new Date(typeof value === "number" && value < 1000000000000 ? value * 1000 : value);
  const formatDate = (value, full = false) => {
    if (!value) return "—";
    const date = asDate(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("ru-RU", full ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  const runPath = (id) => "/api/runs/" + encodeURIComponent(id);
  const requestId = () => globalThis.crypto?.randomUUID?.() || "ui-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
  const describeError = (error) => error?.name === "AbortError" ? "Сервер не ответил вовремя. Проверьте соединение и повторите действие." : safeText(error?.message || error || "Неизвестная ошибка", 2000);

  function connection(kind, message) {
    state.connected = kind === "online";
    $("connection-pill").dataset.state = kind;
    text("connection-label", { online: "Сервер на связи", pending: "Подключаемся", offline: "Нет соединения", auth: "Нужен токен" }[kind] || message);
    text("sidebar-status", message || { online: "Локальный сервер доступен", pending: "Проверяем соединение…", offline: "Сервер недоступен", auth: "Настройте доступ к серверу" }[kind]);
  }
  async function api(path, options = {}) {
    if (!token) { connection("auth"); throw new Error("Добавьте токен локального сервера через настройки подключения в левом нижнем углу."); }
    const controller = new AbortController();
    const requestToken = token;
    const timeout = setTimeout(() => controller.abort(), path === "/api/capabilities" ? 40000 : 15000);
    try {
      const response = await fetch(path, { ...options, cache: "no-store", credentials: "omit", signal: controller.signal, headers: { Authorization: "Bearer " + requestToken, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers } });
      if (requestToken === token && (response.status === 401 || response.status === 403)) connection("auth");
      if (!response.ok) {
        let detail = "";
        try { const body = await response.json(); detail = typeof body.error === "object" ? body.error.message : body.error || body.detail || body.message; } catch { /* Keep HTTP status if no JSON error exists. */ }
        throw new Error(response.status === 401 || response.status === 403 ? "Токен не принят. Откройте настройки подключения и укажите актуальный токен сервера." : "HTTP " + response.status + (detail ? ": " + safeText(detail, 2000) : ". Не удалось выполнить запрос."));
      }
      if (options.binary) return await response.blob();
      if (response.status === 204) return null;
      return await response.json();
    } catch (error) {
      if (requestToken === token && (error instanceof TypeError || error.name === "AbortError")) connection("offline");
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function renderCapabilities(data) {
    state.capabilities = data;
    text("capability-details", data);
    const codex = data?.codex || {};
    const provider = data?.provider || {};
    const sandbox = data?.sandbox || {};
    text("engine-status", codex.available === true ? "Codex" + (codex.version ? " · " + codex.version : " доступен") : codex.available === false ? "Codex не найден" : "Нет данных о Codex");
    $("engine-light").className = "capability-light" + (codex.available === true ? " ready" : codex.available === false ? " warning" : "");
    text("provider-status", provider.ready === true ? "Провайдер готов" : provider.state === "pending" ? "Ожидает подключения" : provider.ready === false ? "Требуется подключение" : "Нет данных о провайдере");
    $("provider-light").className = "capability-light" + (provider.ready === true ? " ready" : provider.ready === false ? " warning" : "");
    const sandboxAvailable = sandbox.available ?? sandbox.supported;
    text("sandbox-status", data?.execution?.root_access ? "ROOT · без изоляции" : sandboxAvailable === true ? sandbox.mode || sandbox.type || "Доступна" : sandboxAvailable === false ? "Недоступна" : sandbox.mode || sandbox.type || sandbox.policy || "Нет данных об изоляции");
    $("sandbox-light").className = "capability-light" + (sandboxAvailable === true ? " ready" : sandboxAvailable === false ? " warning" : "");
    if (provider.ready === false && provider.reason) {
      feedback("notice", "Провайдер: " + safeText(provider.reason, 2000), "info");
      appendSetupLink(provider.setup_url);
    }
  }
  function appendSetupLink(value) {
    if (!value) return;
    let url;
    try { url = new URL(value); } catch { return; }
    if (!["http:", "https:"].includes(url.protocol)) return;
    const link = element("a", "setup-link", "Открыть вход ChatGPT ↗");
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    $("notice").append(link);
  }
  function renderRuns() {
    const list = $("run-list"); list.replaceChildren();
    if (!state.runs.length) { const note = element("p", "sidebar-empty", "Здесь появится история ваших запусков."); list.append(note); return; }
    state.runs.forEach((run) => {
      const button = element("button", "run-item" + (run.id === state.run?.id ? " selected" : ""));
      button.type = "button"; button.setAttribute("aria-pressed", String(run.id === state.run?.id));
      button.append(element("span", "run-item-title", run.prompt || run.id), element("span", "run-item-meta", (statusNames[run.status] || run.status || "Нет статуса") + " · " + formatDate(run.created_at, true)));
      button.addEventListener("click", () => selectRun(run)); list.append(button);
    });
  }
  function elapsed(run) {
    if (!run?.created_at) return "—";
    const start = asDate(run.created_at).getTime();
    const end = terminalStates.has(run.status) || ["paused", "uncertain", "interrupted"].includes(run.status) ? asDate(run.updated_at || run.created_at).getTime() : Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end)) return "—";
    const seconds = Math.max(0, Math.floor((end - start) / 1000));
    return (seconds >= 3600 ? Math.floor(seconds / 3600) + ":" : "") + String(Math.floor(seconds / 60) % 60).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
  }
  function renderRun() {
    const run = state.run;
    if (!run) return;
    const status = run.status || "unknown";
    text("mission-title", terminalStates.has(status) ? status === "completed" ? "Результат готов" : "Запуск остановлен" : status === "running" ? "Идея в работе" : "Задача сохранена");
    text("mission-description", run.prompt || run.id);
    text("run-status", statusNames[status] || status); $("run-status").dataset.state = status;
    $("mission-orbit").dataset.state = status;
    const checkpoint = run.checkpoint || {};
    const step = run.step_count ?? run.steps ?? checkpoint.step_count ?? checkpoint.steps ?? checkpoint.step ?? null;
    text("metric-steps", typeof step === "number" ? step + (run.limits?.max_steps ? " / " + run.limits.max_steps : "") : "—");
    text("metric-time", elapsed(run)); text("metric-mode", run.mode === "live" ? "LIVE" : run.mode || "—");
    text("checkpoint-value", typeof checkpoint === "string" ? checkpoint : checkpoint.created_at ? formatDate(checkpoint.created_at) : checkpoint.id || (Object.keys(checkpoint).length ? "Сохранена" : "Ещё не создана"));
    feedback("run-error", state.operationError || (run.error ? safeText(run.error, 3000) : ""));
    const paused = ["paused", "waiting_provider", "waiting_model", "waiting_approval", "waiting_user", "interrupted"].includes(status);
    $("run-actions").hidden = terminalStates.has(status);
    $("pause-run").hidden = paused; $("resume-run").hidden = !paused;
    ["pause-run", "resume-run", "cancel-run"].forEach((id) => { $(id).disabled = state.actionBusy; });
    const pending = ["waiting_provider", "waiting_model"].includes(status);
    const waitEvent = [...state.events].reverse().find((event) => event.data?.detail && (event.data.status === status || String(event.type).includes("status")));
    const waitDetail = waitEvent?.data?.detail;
    feedback("provider-pending", waitDetail && paused ? safeText(waitDetail, 3000) : pending ? "Для следующего шага требуется провайдер модели. " + (state.capabilities?.provider?.reason || "Подключите ChatGPT и нажмите «Продолжить».") : status === "waiting_user" ? "Среде нужно ваше действие. Проверьте последние события и параметры задачи перед продолжением." : "", "info");
    renderContext();
  }
  function renderContext() {
    const source = state.context || state.run?.context || state.run?.checkpoint?.context;
    const used = source?.used_tokens ?? source?.input_tokens ?? source?.tokens ?? source?.total_tokens;
    const maximum = source?.max_tokens ?? source?.context_window ?? source?.budget;
    const valid = typeof used === "number" && Number.isFinite(used) && used >= 0;
    const percent = valid && typeof maximum === "number" && maximum > 0 ? Math.min(100, Math.round(used / maximum * 100)) : null;
    text("context-value", valid ? used.toLocaleString("ru-RU") : "—"); text("context-unit", valid ? "токенов" + (maximum ? " / " + maximum.toLocaleString("ru-RU") : "") : "нет данных");
    text("context-percent", percent == null ? "—" : percent + "%");
    $("context-fill").style.width = percent == null ? "0%" : percent + "%";
    if (percent == null) $("context-progress").removeAttribute("aria-valuenow"); else $("context-progress").setAttribute("aria-valuenow", String(percent));
    const compactions = state.events.filter((event) => String(event.type).includes("compact")).length;
    text("context-description", compactions ? "Сжатий в журнале: " + compactions + ". Контрольные точки помогают продолжать работу между шагами." : valid ? "Использование контекста по последним данным среды выполнения." : "Данные появятся, когда среда сообщит об использовании контекста.");
  }
  function eventSummary(event) {
    const data = event.data;
    const title = eventNames[event.type] || String(event.type || "Событие").replaceAll("_", " ");
    if (data && typeof data === "object") return title + (data.tool || data.tool_name ? " · " + (data.tool || data.tool_name) : "");
    return title;
  }
  function renderEvents() {
    const list = $("events"); const expanded = new Set([...list.querySelectorAll("details[open]")].map((node) => node.dataset.eventId));
    const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    list.replaceChildren(); $("events-empty").hidden = state.events.length > 0;
    text("event-count", state.events.length + " событий");
    state.events.slice(-250).forEach((event, index) => {
      const item = element("li", "event-item"); item.dataset.type = String(event.type || "");
      const body = element("div", "event-body"); body.append(element("p", "event-summary", eventSummary(event)));
      if (event.data != null) {
        const details = element("details", "event-details"); details.dataset.eventId = String(event.id ?? index); details.open = expanded.has(details.dataset.eventId);
        const preview = typeof event.data === "string" ? event.data : event.data.message || event.data.summary || "Детали события";
        details.append(element("summary", "", safeText(preview, 160)), element("pre", "", safeText(event.data, 24000))); body.append(details);
      }
      item.append(element("span", "event-marker"), body, element("time", "event-time", formatDate(event.created_at))); list.append(item);
      const data = event.data;
      if (data && typeof data === "object") {
        if (data.context || data.usage) state.context = data.context || data.usage;
        else if (String(event.type).includes("context") && (data.used_tokens != null || data.tokens != null)) state.context = data;
      }
    });
    if (nearBottom) list.scrollTop = list.scrollHeight;
    renderContext();
    if (state.run) renderRun();
  }
  function formatSize(size) {
    if (typeof size !== "number" || !Number.isFinite(size)) return "Размер не указан";
    return size < 1024 ? size + " Б" : size < 1024 * 1024 ? (size / 1024).toFixed(1) + " КБ" : (size / 1024 / 1024).toFixed(1) + " МБ";
  }
  function renderArtifacts() {
    const list = $("artifact-list"); list.replaceChildren(); text("artifact-count", state.artifacts.length); $("artifacts-empty").hidden = state.artifacts.length > 0;
    const selectedId = state.run?.id;
    state.artifacts.forEach((artifact) => {
      const item = element("li", "artifact-item"); const info = element("div", "artifact-info");
      const name = element("span", "artifact-name", artifact.name); name.title = safeText(artifact.name);
      info.append(name, element("span", "artifact-meta", formatSize(artifact.size) + (artifact.media_type ? " · " + artifact.media_type : "")));
      const download = element("button", "artifact-download", "↓"); download.type = "button"; download.setAttribute("aria-label", "Скачать " + safeText(artifact.name));
      download.addEventListener("click", async () => {
        download.disabled = true; feedback("artifacts-feedback", "");
        try {
          const blob = await api(runPath(selectedId) + "/artifact/" + encodeURIComponent(artifact.name), { binary: true });
          const url = URL.createObjectURL(blob); const link = element("a"); link.href = url; link.download = artifact.name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (error) { feedback("artifacts-feedback", describeError(error)); } finally { download.disabled = false; }
      });
      item.append(element("span", "artifact-icon", "▧"), info, download); list.append(item);
    });
  }
  async function selectRun(run) {
    state.generation += 1; state.run = run; state.events = []; state.artifacts = []; state.context = null; state.operationError = "";
    feedback("events-feedback", ""); feedback("artifacts-feedback", ""); renderRuns(); renderRun(); renderEvents(); renderArtifacts();
    await refreshDetails(true);
  }
  async function refreshDetails(force = false) {
    if (!state.run || (state.detailBusy && !force)) return;
    const id = state.run.id; const generation = state.generation; state.detailBusy = true;
    const lastId = state.events.length ? state.events[state.events.length - 1].id : 0;
    const results = await Promise.allSettled([api(runPath(id)), api(runPath(id) + "/events?after=" + encodeURIComponent(lastId || 0)), api(runPath(id) + "/artifacts")]);
    if (generation !== state.generation) { state.detailBusy = false; return; }
    const [runResult, eventsResult, artifactsResult] = results;
    if (runResult.status === "fulfilled") {
      const run = runResult.value?.run || runResult.value;
      if (run?.id) { state.run = run; const index = state.runs.findIndex((entry) => entry.id === run.id); if (index >= 0) state.runs[index] = run; renderRun(); renderRuns(); }
    } else feedback("run-error", describeError(runResult.reason));
    if (eventsResult.status === "fulfilled") {
      const incoming = eventsResult.value?.events || [];
      const ids = new Set(state.events.map((event) => String(event.id)));
      const added = incoming.filter((event) => event.id == null || !ids.has(String(event.id)));
      if (added.length) { state.events.push(...added); renderEvents(); }
      feedback("events-feedback", "");
    } else feedback("events-feedback", describeError(eventsResult.reason));
    if (artifactsResult.status === "fulfilled") { state.artifacts = artifactsResult.value?.artifacts || []; renderArtifacts(); feedback("artifacts-feedback", ""); }
    else feedback("artifacts-feedback", describeError(artifactsResult.reason));
    state.detailBusy = false;
  }
  async function refresh() {
    if (state.refreshBusy) return;
    state.refreshBusy = true; $("refresh").disabled = true;
    const results = await Promise.allSettled([api("/api/capabilities"), api("/api/runs")]);
    const [capabilities, runs] = results;
    if (results.every((result) => result.status === "fulfilled")) { connection("online"); feedback("notice", ""); text("updated-at", "Обновлено в " + formatDate(new Date())); }
    if (capabilities.status === "fulfilled") renderCapabilities(capabilities.value);
    else feedback("notice", describeError(capabilities.reason));
    if (runs.status === "fulfilled") {
      state.runs = Array.isArray(runs.value?.runs) ? runs.value.runs : [];
      renderRuns();
      if (!state.run && state.runs.length) await selectRun(state.runs[0]);
    } else feedback("notice", describeError(runs.reason));
    state.refreshBusy = false; $("refresh").disabled = false;
  }
  async function control(action) {
    if (!state.run || state.actionBusy) return;
    const generation = state.generation; state.actionBusy = true; state.operationError = ""; renderRun();
    try {
      const result = await api(runPath(state.run.id) + "/" + action, { method: "POST", body: "{}" });
      if (generation !== state.generation) return;
      state.run = result?.run || result; feedback("run-error", ""); await refreshDetails();
    } catch (error) { if (generation === state.generation) state.operationError = describeError(error); }
    finally { state.actionBusy = false; renderRun(); }
  }
  $("run-form").addEventListener("submit", async (event) => {
    event.preventDefault(); if (state.submitting || !$("run-form").reportValidity()) return;
    const prompt = $("prompt").value.trim(); const workspace = $("workspace").value.trim();
    if (!prompt || !workspace) { feedback("form-feedback", "Укажите описание задачи и рабочую папку."); return; }
    const payload = { prompt, workspace, verify_command: $("verify-command").value.trim(), limits: { max_steps: Number($("max-steps").value), max_seconds: Number($("max-minutes").value) * 60 }, mode: "live" };
    const fingerprint = JSON.stringify(payload);
    if (state.retryRequest?.fingerprint !== fingerprint) state.retryRequest = { fingerprint, id: requestId() };
    payload.request_id = state.retryRequest.id;
    state.submitting = true; $("launch").disabled = true; text("launch-label", "Создаём задачу…"); feedback("form-feedback", "");
    try {
      const result = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) }); const run = result?.run || result;
      if (!run?.id) throw new Error("Сервер не вернул идентификатор запуска. Обновите список задач перед повторной отправкой.");
      state.retryRequest = null; storage.set("relaykite.workspace", workspace); $("prompt").value = "";
      state.runs = [run, ...state.runs.filter((entry) => entry.id !== run.id)]; await selectRun(run);
      feedback("form-feedback", "Задача создана. Ход выполнения появится в журнале.", "success");
      $("mission-title").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "nearest" });
    } catch (error) { feedback("form-feedback", describeError(error)); }
    finally { state.submitting = false; $("launch").disabled = false; text("launch-label", "Запустить задачу"); }
  });
  $("prompt").addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); $("run-form").requestSubmit(); } });
  $("new-run").addEventListener("click", () => { $("prompt").focus(); $("prompt").scrollIntoView({ block: "center" }); });
  $("refresh").addEventListener("click", async () => { await refresh(); await refreshDetails(); });
  $("pause-run").addEventListener("click", () => control("pause"));
  $("resume-run").addEventListener("click", () => control("resume"));
  $("cancel-run").addEventListener("click", () => control("cancel"));
  $("connection-settings").addEventListener("click", () => { $("token-input").value = ""; $("settings-dialog").showModal(); $("token-input").focus(); });
  $("close-settings").addEventListener("click", () => $("settings-dialog").close());
  $("settings-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const value = $("token-input").value.trim(); if (!value) return;
    token = value; storage.set(tokenKey, token); $("token-input").value = ""; feedback("settings-feedback", "Проверяем соединение…", "info"); connection("pending");
    await refresh();
    if (state.connected) { $("settings-dialog").close(); feedback("settings-feedback", ""); await refreshDetails(); }
    else feedback("settings-feedback", "Подключение не установлено. Проверьте токен и доступность локального сервера.");
  });
  $("workspace").value = storage.get("relaykite.workspace");
  if (!token) { connection("auth"); feedback("notice", "Для начала добавьте токен локального сервера. Откройте настройки подключения в левом нижнем углу.", "info"); }
  else refresh();
  let pollCount = 0;
  const timer = setInterval(() => {
    if (document.hidden || state.stopped || !token) return;
    pollCount += 1;
    if (pollCount % 5 === 0) refresh();
    refreshDetails();
    if (state.run) text("metric-time", elapsed(state.run));
  }, 3000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && token) { refresh(); refreshDetails(); } });
  window.addEventListener("pagehide", () => { state.stopped = true; clearInterval(timer); });
});
