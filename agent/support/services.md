# Codaki Mini Codex 0.2.2: service reference

The release worker executes authorized tools on Android. The model in the chat makes decisions; the phone has no independent background AI model.

## Installed release paths

- Magisk module and boot wrapper: `/data/adb/modules/mini_codex`, `service.sh`.
- Packaged code: `/data/adb/modules/mini_codex/agent/phone_agent.py`, `native_phone.py`, `support_runtime.py`.
- Private owner storage: `/data/adb/mini-codex`. Credentials are in `config.json`; do not read or export them for ordinary diagnostics.
- Inventory: `/data/adb/mini-codex/support/passport.json`. Guides may be packaged in the module or installed in the private support directory. Use the paths returned by `phone_status.support`.
- Worker journal and log: `/data/adb/mini-codex/state/jobs.sqlite3`, `state/agent.log`; bounded startup diagnostics: `/data/adb/mini-codex/startup.log`.
- Existing notes and compressed archives: `/data/adb/mini-codex/memory`. Their shared storage budget includes job records and logs. Reuse this memory for confirmed maintenance lessons.
- Runtime: `/data/data/com.termux/files/usr/bin/python`. Retain Termux and its Python installation.

## Diagnose and verify

Start with `phone_status` and search relevant existing memory. A passport records installation metadata, not proof that a service is running. Recheck affected paths, processes and module enable markers before changing them. Refresh using the command returned by `support.refresh_command` after component changes or when stale.

Network dependencies differ between owners. Check the owner's verified configuration and current routes without exporting proxy URLs or credentials. Other Android control plugins may operate a different display; do not reuse their UI coordinates in Codaki Mini Codex.

Stopping a network component or the worker may cut this connection. Prepare recovery before changing it. When a job is pending, use `phone_job_result`; verify an uncertain result before repeating an action. Restored connectivity requires a new successful phone operation. If the channel remains unavailable, recovery requires the owner on the phone or an independently configured connection.

Root belongs to the local service; installation does not give the ChatGPT APK root. Disabling or removing the Magisk module stops the worker while preserving private configuration and task memory.

## 0.2.2: watchdog and proxy

The Magisk service restarts unexpectedly stopped workers after 15 seconds. The worker flock prevents a second agent; the journal prevents duplicate root jobs. Owner-defined `outbound_proxy` in private config is an optional loopback HTTP listener, e.g. `http://127.0.0.1:17890`; never publish a subscription or secrets. Legacy local installation can have an absent enabled marker and a proxy set in service.sh; migrate these deliberately after backup. See docs/resilient-boot.md.
