# RelayKite — resilient boot

## Resilient boot 0.2.2 and optional local VLESS proxy

- The Magisk service supervises the worker and **restarts it after an
  unexpected exit, with a 15-second delay**. The existing state journal and
  exclusive flock prevent duplicate root job execution.
- It waits for Android boot and Termux Python, and honors disable/remove and
  `enabled` markers. No desktop computer or extra root listener is needed.
- Owners may opt in to a loopback HTTP proxy in their **private**
  `/data/adb/mini-codex/config.json`:
  `"outbound_proxy": "http://127.0.0.1:17890"` (example port).
  Only 127.0.0.1 or ::1 with an explicit port is accepted. No subscription
  links or credentials are bundled; the private HTTPS relay still uses TLS.
- On a legacy personal install, first back up the module, original config,
  memory, and journal. Migrate the *local* proxy address from the old service
  environment into the private `outbound_proxy` key. The legacy install may
  have no `enabled` marker: validate the config and explicitly enable it
  (0600) before reboot. **Do not blindly replace a functioning worker**
  without an independent recovery channel; automatic re-enablement is refused.
- Installing the Magisk module does not install root, reconfigure VLESS, alter
  VPN policy or link a public ChatGPT card to the owner's private App.

Offline tests do not establish end-to-end reboot reliability on other phones.
