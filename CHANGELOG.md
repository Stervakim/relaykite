# Changelog

## 0.2.4 — Tencent memory and Graphify

Original Tencent external FTS/file memory adapter and original Graphify code reader; source/status/device/project/version metadata, read-back and bounded search. Optional memory setup requires Node.js in Termux. Existing Portable Use IPC bridge supports the 12 installed engine operations. No parallel Android sessions or background LLM are claimed. Includes verified installed worker delivery/metrics behavior, memory supervisor recovery and preserved private configuration.

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
