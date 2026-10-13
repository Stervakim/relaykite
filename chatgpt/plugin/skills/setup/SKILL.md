---
name: setup
description: "Install and connect Codaki Mini Codex — телефон for the owner; use for initial setup or a missing phone connection."
---

Download the matching Mini Codex release and SHA256SUMS from the repository below. Verify the checksum and read INSTALL_WITH_CODEX.md inside the Magisk ZIP before phone installation. It requires preinstalled Magisk/root and Termux Python. Use an available authorized phone tool or a selected authorized ADB serial; a mobile chat alone cannot install the module.

For a new owner, follow docs/deploy-private-relay.md from the same source revision: create that owner's private Site with D1 DB and MCP, generate individual PHONE_AGENT_TOKEN and Sites service authorization, and transfer configuration privately through configure.sh. The server pins the authenticated ChatGPT owner; the phone uses its own agent token. A GitHub username, App ID or ZIP import is not device ownership. Preserve a working owner's configuration and memory on upgrade.

Use the personal plugin created by Sites for the new owner. Obtain the actual registered App ID from Sites connection metadata if a card with these bundled skills is needed. Run chatgpt/package_card.py --app-id APP_ID in the extracted installer/source checkout to create the bound card in .private/chatgpt. This creates only an App reference: phone pairing remains the existing configuration step. Keep the bound card private. Reuse the existing Sites card when it already meets the need; do not create a second server.

Verify the connected plugin with phone_status, then fresh read_ui. Confirm the intended device, root and support inventory. Report local installation, relay transport and connected-plugin verification separately. Never claim completion based only on installing this card.

Source and releases: https://github.com/kalabuxova1-hash/codaki-mini-codex
