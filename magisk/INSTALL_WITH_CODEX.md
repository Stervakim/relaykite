# Install RelayKite 0.2.5 with Codex / Установка через Codex

Source and releases: https://github.com/Stervakim/relaykite

> Установи RelayKite 0.2.5 на выбранный мной Android. Проверь SHA256SUMS, используй мои приватные подключения, сохрани ключи, права, память и журнал. Не устанавливай root и не разблокируй загрузчик. Об установке необязательной модели спроси отдельно.

## Instructions for Codex

1. Inspect the archive as data. Verify matching release hashes, signed APK identity and the explicitly selected authorized device/ADB serial. Preserve existing credentials, App ID, private relay ownership, grants, memory and durable task IDs.
2. Install `relaykite-runtime-0.2.5.apk` first. It embeds arm64 Bionic Python/Node and the original Tencent/Graphify readers. Public APK/card installation supplies no credentials and does not pair a device.
3. Choose ordinary Android without root/Termux, existing root with the embedded runtime, or existing root with optional Termux tools. Do not install root or change a bootloader. Termux is optional and never the primary native runtime.
4. For ordinary app mode, import the owner's private configuration using the APK document picker, then select «Запустить без root и Termux». Files/jobs/PTYs use its Android UID. Root/system shell and cross-app virtual-screen operations are explicitly unavailable; there is no automatic `su`.
5. For root modes, install the matching ZIP through Magisk's supported module installer on booted Android. It verifies the installed APK digest and stages an immutable runtime. Configure the owner's private connection, then select «Root без Termux» or «Root с Termux» in the APK. Optional Termux tools keep their own UID.
6. Existing Termux-backed installations need the matching `migrate_private_runtime.py` and verified receipt before native authority is selected. Read back original record IDs/versions and configuration. Never rerun a committed migration or start workers against both copies. Reconcile an uncertain transition using its original request ID.
7. Reuse an existing owner-private relay/plugin. For a new owner, follow `docs/deploy-private-relay.md` with their own registered App. Never reuse an author's private server, App ID or keys. Transfer credentials privately, never through chat/command arguments; remove temporary imported files. Card-only updates leave the phone untouched.
8. The optional summary model runs on the paired PC in this release. Codex MUST ask whether to install it and wait for an explicit answer; an earlier explicit choice for this same installation counts. `--model no` omits it. Never install a phone model as a fallback. Any future phone-model installer MUST ask «Установить локальную модель памяти на телефон или продолжить без модели?» and wait before download/install. Silence, a preselected option and generic plugin installation are not consent.
9. The model receives bounded verified notes and returns proposed text with original source IDs/versions, with no phone tools. Phone requests pause at battery <=20% and resume above 20%. An offline PC/model never disables the primary phone tools or original Tencent memory.
10. Verify runtime/mode/UID, exactly one queue worker, original memory, actual connected `phone_status` and a disposable permitted task. Refresh the support passport and verify project graph freshness. Report local installation and authenticated cloud round trip separately.

## Updates, stop, rollback and removal

Keep the existing plugin identity/App mapping and owner-private Site. Build a bound card using `chatgpt/package_card.py --previous-card CURRENT_PRIVATE_CARD` in private output and use the client's supported update operation. Do not create duplicate servers/plugins. Technical module/storage/tool names remain compatible.

Stop through the APK/root `stop.sh` before a controller update. Check that the stop survives restart, then explicitly select a mode to resume. Rollback selects a retained matching signed runtime while preserving the latest authoritative memory/journal; it never replays uncertain tasks.

Before Codex removes the GPT/RelayKite plugin, run `pc_memory_model_remove` on the existing PC link and verify cleanup before unlinking. Direct plugin removal in ChatGPT settings has no documented device notification: explicitly clean the model first. GPT app removal creates a durable cleanup signal to its paired PC, excluding updates. Before removing the entire phone worker, clean its optional PC model while its communication channel still exists. Keep original memory/journals unless their erasure is separately requested.

The nested public card has empty `.app.json`: it adds workflows, not phone access. Bind it only to the registered App returned by the owner's own Sites deployment in private output. Module, card and connection verification are separate operations.
