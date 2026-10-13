# Android installation

English | [Русский](install-android.ru.md)

RelayKite runs a Python worker on **your rooted phone**. The PC is unnecessary after installation. It sends authenticated outbound HTTPS requests to **your own private relay**; it opens no phone network listener. Connecting that private relay's plugin to ChatGPT remains a separate account setup step. Installing this ZIP does not give the ChatGPT APK a Magisk permission or make the plugin connection automatically.

## Recommended: give the ZIP to Codex

Download `mini-codex-magisk-0.2.4.zip` from the repository's latest release and attach it to a Codex session with device tools or local computer access. Ask Codex to install it using `INSTALL_WITH_CODEX.md` inside the archive. Codex checks the checksum and prerequisites, installs the module, provisions your own private relay/plugin when needed and verifies the connection. Existing working configuration and memory are retained on upgrade.

An existing authorized phone-control channel can perform the phone steps without ADB. For first installation without one, connect your phone to the computer running Codex and approve USB debugging. Codex verifies the selected ADB serial, root and Magisk and uses Magisk's module installer. The ZIP is not an APK. Root/Magisk and Termux Python must already exist; secure first unlock or debugging approval may require you. A phone-only chat without a control channel cannot install the agent by itself.

The detailed instructions below also support manual setup.

## Before installing

1. Unlock/root your own Android device and install Magisk. Keep a recovery method available for your device.
2. Install official [Termux](https://github.com/termux/termux-app#installation). Use an official build and keep Termux add-ons from the same source. Open Termux and run `pkg update` followed by `pkg install python`. Open it once after installation so its private runtime exists. The agent uses `/data/data/com.termux/files/usr/bin/python`; deleting Termux also deletes that runtime.
3. Provision a separate **private** relay following the repository's relay instructions. Obtain its HTTPS base URL, its individual agent credential and, where required, its Sites bypass credential. Do not use another owner's URL or share agent credentials. ChatGPT access to the relay must use the relay's account authorization as well.

## Install and configure

1. Download `mini-codex-magisk-0.2.4.zip` and verify its SHA-256 against the release's `SHA256SUMS`.
2. In Magisk, choose **Modules → Install from storage**, select the ZIP and reboot. Install through Codex using Magisk’s supported module installer, or through the Magisk app; not recovery. A fresh installation remains inactive and makes no relay requests until local configuration succeeds.
3. In Termux, run:

   ```sh
   su -c /data/adb/modules/mini_codex/configure.sh
   ```

   Approve Termux's Magisk root request if prompted. Enter **your** relay HTTPS base URL. The two credential prompts hide input; leave the optional Sites credential empty if your relay does not need it. When Sites requires a bypass header, enter its complete value as `Bearer <your own bypass credential>`. Secrets are written to `/data/adb/mini-codex/config.json` with mode `0600`; private directories use `0700`. Secrets are never put in command-line arguments.

   Alternatively, import an individual configuration file locally:

   ```sh
   su -c '/data/adb/modules/mini_codex/configure.sh --import /storage/emulated/0/Download/my-relay.json'
   ```

   The JSON fields are `relay_url`, `agent_token` and optional `sites_authorization`; the agent credential needs at least 40 non-whitespace characters. Use a cryptographically generated 64-character hexadecimal credential, as in the relay setup. Imported files must be regular files; storage paths containing symbolic links are rejected. Delete the downloaded credential file after importing it. An existing configuration is replaced only after you type `REPLACE` locally. A cancelled import keeps the old configuration and state.
4. Reboot, unlock the phone once if storage is encrypted, and connect **your private relay's plugin** to your ChatGPT account. Check `phone_status` first; its root ID should contain `uid=0`. Verify a disposable file write/read before relying on remote operations. Being installed and being connected to ChatGPT are separate states.

## What runs and what persists

Magisk starts the module's `service.sh` at late start. The worker's nonblocking lock prevents two workers from processing the same state. HTTPS certificate verification stays enabled; redirects carrying credentials are refused. Failed or interrupted actions are recorded and are not silently executed again. An action already running when you stop the agent may complete; query its result before repeating it.

The private base is `/data/adb/mini-codex`. Upgrades preserve its configuration, memory and job journal. Total retained memory, journal and logs is bounded to 5 GiB: memory reserves 16 MiB for the bounded journal/logs. Startup diagnostics share a 64 KiB limit and overwrite on each launch; regular worker logs rotate. Memory holds short summaries/scripts and compressed older notes, not full chat exports, screenshots or APKs. This is persisted context, not model training or automatic expansion of Android permissions. Root tools can change your phone's files and applications when you request those actions.

## Stop, restart and uninstall

For immediate local revocation:

```sh
su -c /data/adb/modules/mini_codex/stop.sh
```

This removes the local enabled marker and terminates the matching worker. Re-import your own configuration, confirming replacement when asked, then reboot to resume. Disabling/removing the module in Magisk also stops future polling; revoke the agent credential at your relay when retiring a device.

Uninstalling the module **preserves** `/data/adb/mini-codex` so a later reinstall can retain memory and action history. To erase it permanently, stop/uninstall the module first, inspect the **exact** directory `/data/adb/mini-codex` in a root file manager, verify it is a real directory rather than a link, and delete only that directory. No automatic purge runs during installation or removal.

## Host-only release checks

From the repository root, with Python installed:

```sh
python -m unittest discover -s agent -p 'test_standalone.py'
python -m unittest discover -s tests -p 'installer_*.py'
python scripts/build_release.py
```

The build writes `dist/mini-codex-magisk-0.2.4.zip`, `dist/SHA256SUMS`, and redistributable agent files in `dist/agent/`. These commands do not access a phone or include any owner's configuration.

### Update with GPT

**A new version is out → download the new ZIP → give the file to GPT → ask it to update the plugin.**

> Update this RelayKite plugin from the new ZIP. Keep my phone connection, private server, keys, memory and journal. Check the version and checksum, update the existing card, and verify the connection. If this is the full installer, also update the phone components using INSTALL_WITH_CODEX.md.

The bundled update workflow retains your existing App reference and ChatGPT owner binding. A card-only update leaves the phone runtime unchanged. GPT uses the client's available update/import tools; if the client requires a manual import, it prepares the replacement ZIP and tells you that final step. The file must come from this project's Releases. [Card setup and updates](../chatgpt/README.md).


### Обновление через GPT

**Вышла новая версия → скачайте новый ZIP → передайте файл GPT → попросите обновить плагин.**

> Обнови этот плагин RelayKite из нового ZIP. Сохрани подключение моего телефона, личный сервер, ключи, память и журнал. Проверь версию и контрольную сумму, обнови существующую карточку и проверь связь. Если это полный установщик, также обнови компоненты телефона по INSTALL_WITH_CODEX.md.

Встроенная инструкция обновления сохраняет существующий App ID и привязку к аккаунту ChatGPT владельца. Обновление одной карточки не меняет компоненты телефона. GPT использует доступные средства обновления/импорта; если клиент требует ручного импорта, он подготовит новый ZIP и укажет этот последний шаг. Берите файл из Releases этого проекта. [Настройка и обновление карточки](../chatgpt/README.md).
