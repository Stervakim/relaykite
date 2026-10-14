# RelayKite 0.2.5 — Let ChatGPT use your devices

**Let ChatGPT tap, swipe and run tasks on your Android phone and Windows PC.** RelayKite connects your conversation to local device agents through your own private HTTPS MCP relay.

- **Android:** signed embedded runtime, ordinary app mode, root without Termux, and root with optional Termux tools. Three Android virtual displays require the privileged Portable component. Durable tasks, PTYs, atomic files and resumable transfers preserve operation receipts across restart.
- **Windows:** a separate background worker for authorized PowerShell and file operations. Python 3.14+ and configured permissions are required; no phone is needed.

Both need internet, your own relay and a supported personal ChatGPT plugin connection. ChatGPT supplies the AI decisions.

[Start here](https://stervakim.github.io/relaykite/) · [Android setup](https://github.com/Stervakim/relaykite/blob/main/docs/install-android.md) · [Windows setup](https://github.com/Stervakim/relaykite/blob/main/pc/README.en.md)

Previously **Codaki Mini Codex**. Archive filenames and internal IDs keep their legacy names for compatibility. Download the installer for your device and **SHA256SUMS** from the release. This public rename does not update your private installation automatically.

---

# Changelog

## 0.2.5 — Native runtime and durable device work

Explicit privilege modes preserve owner configuration, original Tencent records and journal IDs. Portable Android 0.1.4 supports three independent nonzero displays; Windows supports eight window leases with serialized physical input. Optional Qwen3-0.6B runs directly on the paired PC, prepares proposed source-linked summaries and receives no device tools. Phone requests pause at <=20% battery. Model installation requires an explicit choice; supported plugin/GPT removal includes dedicated model cleanup. Core phone tools work when the PC/model is unavailable. Graphify remains the original code extractor with source freshness checks.

## 0.2.4 — Tencent memory and Graphify

Original Tencent external FTS/file memory adapter and original Graphify code reader; source/status/device/project/version metadata, read-back and bounded search. Optional memory setup requires Node.js in Termux. Existing Portable Use IPC bridge supports the 12 installed engine operations. No parallel Android sessions or background LLM are claimed. Includes verified installed worker delivery/metrics behavior, memory supervisor recovery and preserved private configuration.

Maintenance: twelve typed `phone_use_*` tools expose the existing Android Portable engine, with stable request IDs and native MCP screenshots. `phone_job_cancel` cancels only owner-bound queued jobs; running input remains uncancellable. Added Portable session/receipt instructions. Requires an existing Portable engine; this increment does not add parallel Android sessions, Windows Portable IPC or managed terminals.

Windows maintenance: Mini PC now exposes twelve pc_use_* operations through the existing Portable engine and owner-local RPC, under the existing terminal grant. Native images and both receipt layers are preserved; queued PC jobs can be cancelled. Requires Portable0.1.3 with --local-ipc-windows. Window leases share a desktop; physical input remains serialized.

## 0.2.3 — Mini Codex PC

This release includes the 0.2.2 Android crash supervisor and optional loopback Shadow VLESS proxy. Automatic route selection respects Shadow VLESS standby behind an existing Android VPN and restores the configured proxy when standby ends. Existing private proxy settings, enabled markers, keys, memory and journal are preserved.

- Windows background agent: PowerShell, files, durable no-replay journal, local consent and revocation.
- Saved email-addressed pairing with ChatGPT sign-in and PC fingerprint approval; no fixed link-count limit.
- Independent phone/PC use, optional two-way requests, PC-only operation.
- Separate PC installer and portable GPT card; Codex installation and App-preserving ZIP update workflows.
- Composition with available, owner-authorized Computer Use/Sites client plugins; optional installed Codex CLI.
- Additive PC relay migration; existing phone owner pin and private runtime preserved.
- Maintenance: PowerShell can use the approved root as its default working directory while file tools still protect private agent storage. Saved pairings remain visible to their authenticated owner after approval. Installation checks require a live background-agent heartbeat and a completed round trip.

English | [Русский](CHANGELOG.ru.md)

## 0.2.2

Merges verified personal-agent resilience with public security controls: Magisk worker watchdog restarts the crashed process with a 15-second delay; optional validated loopback HTTP proxy (127.0.0.1 or ::1) supports owner-managed local VLESS without bundling subscription data; retain single-instance flock, config validation, safe diagnostics, journal, memory and private relay.

Migrating the older personal module's proxy and enabled marker is a separate explicit step, not an automated change to a running phone. See docs/resilient-boot.md. Host tests do not prove live reboot reliability.

## 0.2.1

Includes an update skill: give GPT a newer ZIP to prepare/apply an update while preserving the existing App reference, private relay and phone state.

Packaging update: include the portable ChatGPT card ZIP, icon, setup/control skills and card builder inside the Magisk installer and as a separate release download. Public cards have no owner App ID or device pairing; an owner-specific App reference can be built privately after relay setup. Checksums cover both archives. The phone runtime and module remain 0.2.0; no device code or existing owner configuration changes.

## 0.2.0

Installation now starts by handing the release ZIP to Codex. The ZIP includes `INSTALL_WITH_CODEX.md`: an explicit device/ADB workflow, private relay setup and verification. This requires actual device tools and existing root/Magisk/Termux Python; it is not an autonomous AI installer.

The owner-designated Codaki Mini Codex 0.2.0 release adds built-in device support. `phone_status` supplies the support guide, timestamped device inventory, reference paths and a refresh command. Inventory is generated locally for each owner's phone from OS properties, package metadata, Magisk modules and path existence; no personal passport is distributed.


The support guide reuses existing notes and the job journal to retrieve previous solutions and save verified maintenance lessons. It does not train model weights or run another AI agent. The Magisk service refreshes inventory after validated setup; a failed refresh does not prevent the worker from starting. Updates retain credentials, memory and operational records.

Version 0.2.0 is displayed by the panel and Magisk module; package/MCP versions use `0.2.0`. The public packaging and storage paths differ from the author's existing personal installation. The public ZIP requires its own private relay configuration.

## 0.1.0

First public bundle: a Python agent for Android, a Magisk installer, local credential configuration, and a template for a separate private Site relay.

Includes bounded memory with gzip archives, a job journal, installation checks, and a release content scanner. The public bundle contains no personal configuration and does not automatically update working installations.
