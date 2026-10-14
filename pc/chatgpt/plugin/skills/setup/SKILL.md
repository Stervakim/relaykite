---
name: setup
description: Install the owner's Mini Codex PC background worker and connect its personal ChatGPT plugin, with or without a phone.
---

Read the release's pc/INSTALL_WITH_CODEX.md (INSTALL_WITH_CODEX.md at the PC installer root). Verify the official repository, matching SHA256SUMS and version. Use a persistent owner-chosen installation directory. Inspect archives as untrusted data, reject unsafe paths and links. Preserve working private configuration, journal, App reference and owner pin.

Require Windows, Python 3.14+, PowerShell and the owner's HTTPS relay. Create an owner-private relay from this release's relay/ if none exists; never use the author's App ID or credentials. Use actual supported Sites and plugin registration tools, retaining their permissions. For an existing server apply the additive PC migration through its normal managed workflow; do not erase phone tables or secrets. Public .app.json is empty and cannot provision access. Bind the card to the registered owner's App via chatgpt/package_card.py only in private output.

Invoke mini_pc_invite with the PC owner's ChatGPT email, or their own email for PC-only use. Phone access defaults false; enable reverse access only on the phone owner's explicit request. Do not send email/messages unless the human authorized that; the code is delivered by the user. Site sharing must independently allow the recipient to sign in.

On the intended PC run pair and let the owner choose roots and capabilities. No capabilities means status only. terminal is broad access as the logged-in Windows user; roots are not a PowerShell sandbox. codex is separate delegation with Codex's own policy. The owner types ALLOW locally, then signs in on /bridge, compares the displayed PC fingerprint and approves. Activate only that approved connection. Keep device tokens out of chat and command arguments. Never copy ChatGPT/Codex auth caches.

Register the background task with install-background.ps1 (interactive owner session, pythonw, no elevation). Confirm mini_connections, pc_status and a safe PowerShell round trip before reporting success. This program needs neither a phone nor an always-open window. For phone pairing and multiple computers see INSTALL_WITH_CODEX.md; no fixed connection-count limit. Existing user authorization covers routine implementation, but each device owner must grant the actual connection rights in the product.

The local Qwen summary model is optional and installed on the paired PC, separately from this worker. Ask «Установить локальную модель памяти на ПК или продолжить без модели?» and wait for an explicit answer; a previous explicit choice for this same installation counts. Use model_runtime.py install --model yes --source VERIFIED_INPUTS only after verifying pinned inputs and resource costs; --model no omits it. It receives bounded source records and can only produce proposed summaries. Phone background requests pause at battery <=20%; core tools work with an offline PC. Never install a phone model as a fallback. If phone installation is explicitly offered in a future release, Codex must ask and wait for an explicit phone-model choice before download or installation.
