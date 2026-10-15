# RelayKite autonomous development

The 0.3.0 development track adds original Codex 0.154.0 to the existing ChatGPT
plugin. ChatGPT remains the conversation interface. A local service executes
tools and requests model decisions through ordinary saved ChatGPT conversations.
A run can continue after the invoking response ends. Internet, login, supported
account features and available quota remain required. Temporary chats and model
API keys are not used by this transport.

## Installation and lifecycle

Use the matching signed runtime APK and Magisk component, with the release
SHA-256 inventory. ARM64 Android and existing root are required for development.
Python and Node are embedded; no Termux process or PC is needed at runtime.
Configure your own private relay; public templates contain no owner connection.

Call relaykite_dev capabilities first. If the engine is absent, install starts
a managed installation job: retrieve its original receipt before checking
capabilities again. The installer verifies the shipped upstream SHA-256 lock,
resolves native dependencies and executes Codex, Git and ripgrep before atomic
activation. Existing engines and owner policy are preserved. Rolling upstream
servers can remove pinned inputs: an unavailable archive is an error, never
permission to substitute unverified code. Lock updates require review and
repeated execution checks. The Bionic Git build inputs come from the official
Termux package registry; their licenses/provenance remain distinct from MIT.

Start receives prompt, an existing absolute workspace within configured roots,
optional verify_command and bounded limits. Retain the returned run identifier.
A transport pending job_id is not a run identifier. Inspect the same run through
status, events and artifacts; use pause, resume or cancel to control it.
Keep a mutation request_id stable for transport retries; each new poll uses a
fresh ID. Inspect uncertain receipts/live state before continuing.
Paused, waiting, failed and cancelled states must not be reported as completed.

Omit connection_id for the phone; explicitly select a paired PC for PC work.
SQLite journals retain runs, events, checkpoints and operation receipts.
Context uses estimates, checkpoint summaries and original Codex text compaction.
The relaykite-agent skill describes routing and truthful lifecycle reports.

Optional additional_relays lets one phone worker poll separate owner-configured
personal plugin relays. Credentials stay private. Durable receipt namespaces
prevent identical transport job IDs from colliding between relays. This does
not automatically grant an account access to another account's personal plugin.

## Execution and compatibility

Android root uses explicit android-root / danger-full-access with no sandbox
isolation on the tested kernel. Workspace policy selects the working folder;
it does not restrict root privileges. Windows separately supports the original
Codex workspace sandbox.

Android tools use Portable root IPC, owned nonzero displays, fresh observations,
target revalidation and durable receipts. The Codex adapter currently exposes
semantic actions and rejects screenshots. It is not a complete vision-based
Computer Use integration. ChatGPT plugins are not automatically available inside
Codex; only configured compatible skills and MCP tools are available to a run.

Login/quota failures, a busy owned display and uncertain actions stop for
inspection. Screen-off, reboot and compatibility across devices require separate
testing. See [verification ledger](development-progress.md). Public packages
must exclude personal relay URLs, accounts, credentials, browser profiles,
conversations and private memory.
