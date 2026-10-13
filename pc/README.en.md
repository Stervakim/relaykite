# RelayKite for Windows — 0.2.4

English | [Русский](README.md)

A background Windows worker connects ChatGPT to authorized PowerShell and file operations through your own private HTTPS MCP relay. It runs as your ordinary Windows user and makes outbound HTTPS requests. No phone is required.

## Install

1. Prepare Python 3.14+ and PowerShell. Verify that your account can use the personal plugin connection.
2. Download `mini-codex-pc-0.2.4.zip`, `codaki-mini-codex-pc-chatgpt-0.2.4.zip` and `SHA256SUMS` from [v0.2.4](https://github.com/kalabuxova1-hash/relaykite/releases/tag/v0.2.4).
3. Give the files to Codex and ask it to verify the checksum and follow the included `INSTALL_WITH_CODEX.md`. The installer archive also contains the plugin card under `chatgpt/`.
4. Configure your private relay, choose allowed folders and explicitly grant the permissions you need. Verify `pc_status` and a small, authorized PowerShell command.

> Install RelayKite for Windows 0.2.4 from this ZIP. Verify SHA256SUMS and read INSTALL_WITH_CODEX.md. Connect my private relay and personal plugin, configure allowed folders and PowerShell permissions, preserve existing pairings, and verify pc_status and a safe command. Set up background startup without a visible window.

Importing the public card alone does not register a PC or grant terminal access. Release archives and technical commands still use the previous Mini Codex names for compatibility.

## Permissions and pairing

Each device pairing has its own credentials, owner confirmation, grants and revocation. New pairings grant status only by default. A ChatGPT email addresses an invitation; email alone does not grant access. Private hosting access remains a separate requirement.

File tools enforce selected folders and reject links/junctions. A `terminal` grant permits PowerShell with the Windows user's privileges: the file-tool folder list is not a PowerShell sandbox. The optional `codex` grant enables an installed and explicitly authorized Codex CLI with its own policies.

ChatGPT can combine RelayKite with tools from other available plugins. The worker does not automatically inherit their credentials or UI sessions. Portable UI operations require the corresponding installed Portable engine and its Windows IPC support.

## Update and stop

Give GPT the new ZIP and its checksum file. Ask it to preserve the existing App ID, pairings, permissions, credentials, memory and journal. Checksums detect changes; they are not cryptographic signatures. An uncertain job result must be inspected before retrying.

`python mini_codex_pc.py stop` blocks subsequent jobs; an already running command may finish. `start` removes the block. `revoke --connection ID` disables that pairing locally and revokes it on the server when online. `mini_disconnect` revokes from the server. `./install-background.ps1 -Remove` removes the background task while preserving configuration and records.

[Detailed installer instructions (Russian)](INSTALL_WITH_CODEX.md) · [Source](mini_codex_pc.py) · [Android guide](../docs/install-android.md)
