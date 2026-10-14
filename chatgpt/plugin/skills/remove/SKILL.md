---
name: remove
description: Remove this owner's RelayKite plugin and optional phone memory model without deleting original memory or other apps.
---

When the owner asks Codex to remove this plugin, first use the existing paired PC channel to stop and remove the optional RelayKite memory model. Remove only the owned model runtime, its processes, weights and private router data. Preserve the main phone/PC workers, original Tencent memory, credentials, journals, Termux and unrelated apps unless their removal is separately requested. Verify the model process and weights are gone, then use the client's supported plugin removal operation. An unavailable PC leaves cleanup pending; say so, and never describe the local model as removed merely because the plugin was unlinked.

Use `pc_memory_model_remove` with no arguments on the same paired PC. It operates only on the recorded dedicated model installation; an arbitrary path or command is forbidden. Read back its removal receipt before unlinking the plugin.

Deleting the plugin directly in ChatGPT settings does not provide a documented device uninstall event. Do not promise automatic detection of that action. Tell the owner to run model cleanup before unlinking. Removal of the GPT app is detected locally by the phone worker and forwarded as a durable cleanup request to its paired PC; app updates must not trigger deletion. If the phone worker itself is removed, use explicit cleanup before uninstalling it.
