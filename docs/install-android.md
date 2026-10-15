# Android installation

English | [Русский](install-android.ru.md)

Check `SHA256SUMS`, then install the signed `relaykite-runtime-0.3.0.apk` from the [matching release](https://github.com/Stervakim/relaykite/releases/tag/v0.3.0). The APK embeds Bionic Python/Node and original Tencent/Graphify. Primary phone tools need the phone, internet and your private relay/plugin; no running PC is needed after setup.

| Mode | Installation and permissions |
| --- | --- |
| Without root or Termux | APK only; ordinary Android UID. Own-permission files, jobs, memory and PTYs. Root/system shells and cross-app virtual-screen control unavailable. |
| Root without Termux | APK first, matching Magisk ZIP second, using existing Magisk. Embedded runtime and privileged tools. |
| Root with Termux | Same native installation; optional preinstalled Termux tools run under their separate UID. |

Select a mode in the APK. Import your own private connection with its document picker on a fresh installation. Fields: `relay_url`, `agent_token`, optional `sites_authorization`. Generate individual strong keys through [private relay setup](deploy-private-relay.md); keep them out of chat/command arguments and delete temporary transfer files. Public APK/card installation never automatically pairs a phone.

Keep an existing owner's server, App ID, keys, grants, memory and journal. For Codex installation, supply the matching release, [INSTALL_WITH_CODEX.md](../magisk/INSTALL_WITH_CODEX.md) and an explicitly selected authorized device/ADB serial. It does not root phones or unlock bootloaders.

Existing Termux installations require the matching private migration before selecting native authority. Verify the receipt and original IDs/versions; never replay a committed migration or run two journal copies. [Runtime modes](runtime-modes.md) describe durable stop, reconciliation and rollback.

Verify connected `phone_status`, actual mode/UID, original memory and a disposable permitted task. APK installation is not pairing verification. Network, Android background policies and first unlock may delay operation. Missing permissions are explicit and never trigger implicit root.

Qwen summaries are optional and run on the paired PC. Codex asks and waits before model installation. No Qwen/OmniRoute is installed on the phone; core tools and Tencent work without it. Phone requests pause at battery <=20% and resume above 20%. Any future phone-model installation requires an explicit phone-model question and answer. [Summary policy and removal](background-summaries.md).

Use the APK mode/stop controls. Root `stop.sh` stops the installed controller; deliberate stops persist through restart/update. Root module removal preserves `/data/adb/mini-codex` for recovery. Before unlinking a plugin or removing the entire phone worker, run `pc_memory_model_remove` and verify cleanup while the existing connection still works. Direct plugin unlink has no documented cleanup event. Erase original memory only when separately requested.

Host checks: `python -m unittest discover -s agent`, `python -m unittest discover -s tests`, `python scripts/build_release.py`. Signed APK building requires pinned SDK/runtime inputs and private signing inputs outside the repository. Owner configuration must never enter public releases.


## Autonomous Codex on Android (0.3.0)

This is an additional mode of the same plugin, not a replacement chat app.
For a fresh rooted ARM64 installation:

1. Verify `SHA256SUMS`. Install the signed runtime APK, then the matching
   `mini-codex-magisk-0.3.0.zip` through the existing Magisk installer.
2. Install `codaki-portable-use-0.1.5-android.zip` as the local UI backend.
   Follow [Portable installation](../portable/CODEX_INSTALL.md). Its installer
   deliberately leaves a `stopped` marker. After reviewing the installation and
   authorizing its start, remove only that marker and start its installed service.
   With no `agent.json`, it uses local root-only IPC: it needs no second ChatGPT
   plugin, cloud relay or copied credentials.
3. Configure your own RelayKite connection and select native root mode. Complete
   any required reboot and first unlock. Verify `phone_status`, root UID and
   Portable capabilities through the actual connected plugin.
4. Ask `relaykite_dev` for `capabilities`, then `install`. The staged installer
   downloads SHA-256-pinned original Codex and Git inputs into private phone
   storage. Poll the returned job receipt; do not retry an uncertain installation.
5. Start a small task with a chosen workspace and explicit `verify_command`.
   Read `status` and `events` until the actual verification succeeds. Use the
   existing `run_id` for pause/resume/cancel; never start a duplicate to poll.

Use an ordinary saved ChatGPT conversation. Root execution has no sandbox on
Android; workspace policy is not kernel isolation. Model image input is disabled.
Account limits, device lock and network failures can pause model delivery.
No always-on PC or Termux process is required after setup.

For an upgrade, preserve private configuration, memory, task/receipt journals,
permissions and intentional stop markers. Keep the original primary relay URL
unchanged during initial legacy-receipt migration. The Portable installer refuses
to overwrite an existing installation: first idle its sessions, back up the
runtime and private state, then follow its reviewed upgrade procedure. Never
remove journals to bypass an uncertain operation. See [development operation](DEVELOPMENT.md).
