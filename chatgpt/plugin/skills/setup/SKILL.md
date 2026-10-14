---
name: setup
description: "Install and connect Codaki Mini Codex — телефон for the owner; use for initial setup or a missing phone connection."
---

Download the matching RelayKite release and SHA256SUMS from the repository below. Verify the checksum and read INSTALL_WITH_CODEX.md before phone installation. Choose ordinary Android without root/Termux, root with the embedded runtime, or root with optional Termux tools. Use an authorized phone tool or an explicitly selected authorized ADB serial; a mobile chat alone cannot install an APK.

The optional summary model for this release runs on the paired PC. Ask whether to install it there or continue without it; wait for an explicit choice. Never install a model on the phone as a fallback. If a future installation offers a phone model, Codex MUST ask the owner: «Установить локальную модель памяти на телефон или продолжить без модели?» and wait for an explicit answer. Silence, a preselected option, installation of this plugin, and a generic request to install RelayKite are not consent. An explicit choice already supplied for this same installation counts; do not ask twice. Record the choice for this installation, not as permanent permission for another device or reinstall.

Explain the verified download and installed size, background memory use, and the battery policy before the choice. The model is optional: all primary phone tools and original memory work without it. If chosen, local Qwen on the PC only prepares proposed memory summaries; it has no phone tools. The phone's background requests run while the paired PC is available, pause at phone battery 20% or below, and resume above 20%. Neither model weights nor OmniRoute are installed on the phone.

For a new owner, follow docs/deploy-private-relay.md from the same source revision: create that owner's private Site with D1 DB and MCP, generate individual PHONE_AGENT_TOKEN and Sites service authorization, and transfer configuration privately through configure.sh. The server pins the authenticated ChatGPT owner; the phone uses its own agent token. A GitHub username, App ID or ZIP import is not device ownership. Preserve a working owner's configuration and memory on upgrade.

Use the personal plugin created by Sites for the new owner. Obtain the actual registered App ID from Sites connection metadata if a card with these bundled skills is needed. Run chatgpt/package_card.py --app-id APP_ID in the extracted installer/source checkout to create the bound card in .private/chatgpt. This creates only an App reference: phone pairing remains the existing configuration step. Keep the bound card private. Reuse the existing Sites card when it already meets the need; do not create a second server.

Verify the connected plugin with phone_status, then fresh read_ui. Confirm the intended device, root and support inventory. Report local installation, relay transport and connected-plugin verification separately. Never claim completion based only on installing this card.

Source and releases: https://github.com/Stervakim/relaykite
