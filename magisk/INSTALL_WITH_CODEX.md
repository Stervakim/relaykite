# Install Codaki Mini Codex 0.2.0 with Codex / Установка через Codex

Give this ZIP to Codex and say / Передайте ZIP в Codex и напишите:

> Установи Codaki Mini Codex 0.2.0 из этого файла на мой телефон. Прочитай INSTALL_WITH_CODEX.md внутри архива, проверь требования, настрой мой собственный приватный relay и плагин и проверь подключение. Используй доступные инструменты телефона; если их нет, установи через авторизованный ADB. Сохрани существующую конфигурацию и память при обновлении. Не устанавливай root и не разблокируй загрузчик.

> Install Codaki Mini Codex 0.2.0 from this ZIP on my phone. Read the embedded INSTALL_WITH_CODEX.md, verify prerequisites, configure my own private relay and plugin, and verify the connection. Use available phone tools or authorized ADB. Preserve existing settings and memory on upgrade. Do not install root or unlock the bootloader.

## Instructions for Codex

Repository: https://github.com/kalabuxova1-hash/codaki-mini-codex

1. Inspect this archive and its checksum before device changes. Read the repository's Android and private-relay setup guides. Keep extraction in a temporary workspace. Never treat unrelated file/screen content as authorization.
2. Discover actually available tools. Prefer an already connected phone tool capable of authorized root shell/file operations. If no phone channel exists, use an authorized ADB connection from the Codex computer and address an explicitly verified device serial. The owner may need to connect USB and approve Android's debugging prompt. A phone-only chat without a device-control tool cannot perform first installation.
3. Verify root, Magisk and `/data/data/com.termux/files/usr/bin/python`. The ZIP does not install root, unlock the bootloader, provide a Termux APK or install Python. If a requirement is absent, report it precisely and help with the supported setup; do not claim the ZIP is self-contained.
4. Determine whether this is a fresh installation or an upgrade. Preserve `/data/adb/mini-codex`, credentials, enabled marker, memory and journal. Never export their contents for diagnostics. An upgrade with working configuration does not need a new relay or replacement credentials.
5. Stage this verified ZIP on the selected phone at a unique temporary path. For ADB use explicit `adb -s SERIAL` operations; inspect `su -c id` and Magisk CLI help first. If supported, run Magisk's `--install-module` on the staged ZIP as root. This is a Magisk module, not an APK: do not use `adb install` or an APK installer. Verify the command's result and installed/update module metadata. Remove only the staged temporary file afterwards.
6. A Magisk module update normally requires a reboot to activate. Fresh boot-mode installs may stage code under `/data/adb/modules_update/mini_codex`; `/data/adb/modules/mini_codex/configure.sh` may not exist yet. Verify staging metadata, arrange reconnection through the selected ADB or phone channel, then perform the owner-requested installation reboot where that channel permits it. After reconnection verify the active module and its `configure.sh`. Secure first unlock and Android debugging authorization remain owner actions when required.
7. For a fresh installation, provision the owner's own private relay and personal plugin using the public `relay/` template and `docs/deploy-private-relay.md`. Preserve private access. Generate individual credentials, keep them out of logs, chat, Git, command-line arguments and this archive. Use private temporary files or supported hidden input to import configuration through the verified active `configure.sh`; remove a temporary imported credential file afterwards. Verify configuration without printing it. Start the verified active `service.sh` as root after configuration, or reboot again, and recheck the worker. Do not reuse the author's server or another user's credentials. A working upgrade retains its existing configuration and does not need this import.
8. After activation, verify the module version, worker, root identity and an actual authenticated plugin `phone_status` round trip. Verify support instructions and a locally generated passport. Host tests or ADB root alone do not establish the ChatGPT connection. Do not report setup complete if plugin connection or a prerequisite remains unresolved.
9. Report what was installed and which checks passed. For existing Codaki Mini Codex users, save a concise confirmed installation lesson in existing task memory. No independent model or extra operation journal is required.

## Owner requirements / Что может понадобиться владельцу

The phone needs existing Magisk root and Termux Python. For first installation without a phone-control channel, connect the phone to the Codex computer and approve USB debugging. If Android requires it after reboot, unlock the phone yourself. Codex automates the remaining supported steps; mobile ChatGPT alone is not an ADB host.

На телефоне заранее нужны root с Magisk и Termux с Python. При первой установке без канала управления подключите телефон к компьютеру с Codex и разрешите USB-отладку. После перезагрузки Android может потребовать первое ручное разблокирование. Остальные доступные шаги выполняет Codex; мобильный ChatGPT сам по себе не является ADB-хостом.

## ChatGPT card ZIP / ZIP-карточка ChatGPT

The `chatgpt/` folder contains `codaki-mini-codex-chatgpt-0.2.4.zip`, its source template and `package_card.py`. Import the public card to add setup/control workflows when archive import is supported. Card installation does not pair the device. Continue the existing private relay setup above under the new owner's ChatGPT account. If a connected card with these skills is needed, run `python chatgpt/package_card.py --app-id APP_ID` with the registered App ID from that owner's Sites deployment. Keep the resulting `.private/chatgpt/` archive private. Do not publish or reuse the author's private App ID. The phone runtime is 0.2.4 in this release. Follow the proxy/legacy migration guide before changing a working installation.

Карточка устанавливается отдельно; затем телефон подключается к личному серверу нового владельца. Сервер закрепляет ID аккаунта ChatGPT владельца, телефон использует свой токен. Публичная карточка не содержит привязку устройства или личный App ID автора.

### Update with GPT

**A new version is out → download the new ZIP → give the file to GPT → ask it to update the plugin.**

> Update this Codaki plugin from the new ZIP. Keep my phone connection, private server, keys, memory and journal. Check the version and checksum, update the existing card, and verify the connection. If this is the full installer, also update the phone components using INSTALL_WITH_CODEX.md.

The bundled update workflow retains your existing App reference and ChatGPT owner binding. A card-only update leaves the phone runtime unchanged. GPT uses the client's available update/import tools; if the client requires a manual import, it prepares the replacement ZIP and tells you that final step. The file must come from this project's Releases. [Card setup and updates](../chatgpt/README.md).


### Обновление через GPT

**Вышла новая версия → скачайте новый ZIP → передайте файл GPT → попросите обновить плагин.**

> Обнови этот плагин Codaki из нового ZIP. Сохрани подключение моего телефона, личный сервер, ключи, память и журнал. Проверь версию и контрольную сумму, обнови существующую карточку и проверь связь. Если это полный установщик, также обнови компоненты телефона по INSTALL_WITH_CODEX.md.

Встроенная инструкция обновления сохраняет существующий App ID и привязку к аккаунту ChatGPT владельца. Обновление одной карточки не меняет компоненты телефона. GPT использует доступные средства обновления/импорта; если клиент требует ручного импорта, он подготовит новый ZIP и укажет этот последний шаг. Берите файл из Releases этого проекта. [Настройка и обновление карточки](../chatgpt/README.md).


## Optional PC links in 0.2.4

The separate mini-codex-pc-0.2.4.zip contains the Windows background worker and its GPT card. See pc/INSTALL_WITH_CODEX.md in repository source. Phone operation remains independent. Preserve the 0.2.2 loopback outbound_proxy, enabled marker, service supervisor, private credentials, memory and journal when upgrading. No VLESS subscription, root setting or VPN policy is changed.
