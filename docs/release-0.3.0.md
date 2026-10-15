# RelayKite 0.3.0 — autonomous original Codex

RelayKite now runs original Codex 0.154.0 on rooted ARM64 Android and continues
development after the invoking ChatGPT reply ends. The interface remains a
ChatGPT plugin: **RelayKite · Codex Android** and **RelayKite · Codex** on PC,
with the same blue icon.

- Native patches, shell, Git, sequential tools and semantic Android MCP.
- Durable runs, event logs, checkpoints and receipts; pause, resume and cancel.
- Bounded context and original Codex compaction.
- Model decisions through ordinary saved ChatGPT conversations, without a model
  API key for that transport. Existing login, quota and network requirements apply.
- Embedded Python/Node and a SHA-256-pinned staged Codex/Git installer. No PC or
  Termux process is required during phone execution after setup.
- Multiple owner-configured relays share one executor, with distinct durable
  receipt namespaces. Each account still connects its own eligible plugin.
- Portable 0.1.5 revalidates checked/selected/action/scrollability state before input.

Install the signed APK and matching Magisk component, then the Portable Android
backend for autonomous ChatGPT transport. Use [Android setup](install-android.md)
or [Russian setup](install-android.ru.md). Keep configuration, credentials,
memory, permissions, journals and intentional stop markers during an upgrade.
The public templates contain no personal connection; deploy your own private relay.

The installed phone completed actual Codex patch/shell/Git and Android MCP runs
with explicit verification. The final reply-binding implementation also completed
a fresh real-model task. Host checks covered 216 repository, 124 agent, three PC,
131 Portable and 22 relay tests, with documented opt-in/platform skips.
See [evidence and limits](development-progress.md).

Android root is unsandboxed. Native model image input is disabled; this release
does not provide the full OpenAI or Anthropic Computer Use stack. Compatible
skills/MCP can be configured, but ChatGPT plugins are not automatically Codex
tools. Screen-off and cross-device behavior need further testing. Initial device
preparation may require a computer and existing root; the installer does not root
devices or bypass the lock screen. Source is MIT; bundled upstream licenses and
provenance remain applicable. ChatGPT and hosting may have their own costs.
