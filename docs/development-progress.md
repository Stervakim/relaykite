# 0.3.0 development verification ledger

Updated 2026-10-15. This file records tested source and installed-device behavior;
the GitHub release state must be checked separately.

Implemented: durable runs/events/receipts/checkpoints, original Codex app-server,
saved-conversation Android/desktop model transports, native patch/shell/Git,
verification continuations, bounded context, original compaction, Android
Portable MCP and owner-granted PC routing. The product interface remains the
ChatGPT plugin. The service inspection page is not a replacement chat.

Verified on Redmi Turbo 3, Android 17, Magisk, embedded Python/Node:

- Signed runtime 0.3.0 and matching Magisk module installed and booted. One
  root worker serves two configured owner relays; both returned HTTP 200 after
  the owner's VPN was enabled. No Termux process is required.
- Original Codex 0.154.0 completed a real patch/shell/Git/Android MCP task and
  explicit file verification. Independent device reads confirmed UID 0, exact
  file contents and Git status.
- After the reply-binding fix, another real task completed three native actions
  through saved ChatGPT, including root/file/Git verification and Android MCP.
- Original thread/compact/start completed; a following turn recalled a control
  fact across three actual model requests. A previous detached task used nine
  model requests and seven native actions.
- A separate fresh engine installation downloaded and checked pinned upstream
  inputs, then executed Codex, Git and ripgrep. Production and fresh Git both
  completed HTTPS GitHub ls-remote with the upstream CA bundle.
- The APK installation blocker was an unrelated installed rotation overlay's
  misaligned resource table. The owner requested its removal; after removal and
  reboot the system table check and APK installation succeeded. No platform
  security check was disabled.

Host checks: 215 repository tests (two skipped), 124 agent tests (ten skipped),
three PC tests, 131 Portable tests (three skipped), 22 relay tests, relay build
and TypeScript checks passed. The repository count excludes opt-in live tests;
real-device acceptance is recorded separately above.

Reviewed regression fixes: per-request model reply binding; installer activation
only after policy preparation; durable legacy relay origin; app-owned runtime
files; Portable input rejection after checked/selected/actions/scrollability
changes. The final installed APK contains the runtime fixes.

Public phone/PC plugin archives include autonomous routing instructions and the
same original blue icon. The existing private App-backed plugin archive update
was rejected by its platform API; it remains at its previous release. Its live
phone_status supplies the updated installed support instructions. Do not report
a private archive release as published. Both owner relays share the executor;
each account must connect its own eligible personal plugin.

Limits: Android root is unsandboxed. Native model image input is disabled;
bundled OpenAI Computer Use and broad screen-off/device compatibility are
unverified. ChatGPT plugins are not automatically native Codex tools. Account,
network and unlock requirements continue to apply. The phone's existing Portable
0.1.4 backend carries the tested engine fix; the complete public companion is
version 0.1.5. Cross-device compatibility still needs testing.
