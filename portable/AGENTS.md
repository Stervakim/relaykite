# Guidance for Codex working in this repository

First read **CODEX_INSTALL.md**. It is the primary owner-approved installation workflow.

The project's installed phone runtime is not this checked-out copy. Do not change Magisk/root/VPN settings or existing module data as a shortcut. Never upload credentials or device logs to GitHub.

Do not claim installation succeeded without the two trusted Java JARs, root/Termux requirements, and actual runtime verification. Do not silently replace components from Android Use; the projects remain separate.

For ordinary code changes, run syntax checks and synthetic regression tests. Real device tests must use only the owned virtual display and be non-destructive.
