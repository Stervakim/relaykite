# RelayKite — AI tasks. Your devices.

![RelayKite: ChatGPT connected to Android and Windows through a private relay](docs/assets/relaykite-cover.png)

**Let ChatGPT tap, swipe and run tasks on your devices.**

Control your Android phone and Windows PC through your own private MCP relay.

[Website](https://stervakim.github.io/relaykite/) · [Download v0.3.0](https://github.com/Stervakim/relaykite/releases/tag/v0.3.0) · [Android setup](docs/install-android.md) · [Windows setup](pc/README.en.md) · [Русский](README.ru.md)

RelayKite gives your AI assistant a way to act on the devices you own. Ask it to inspect your phone, open an app, work with files, or run an authorized PowerShell task on your PC. ChatGPT plans the task; a local agent carries it out and returns the result.

**The Android agent runs on the phone itself.** After setup, everyday phone control does not require a permanently running computer, USB or desktop ADB. The Windows agent runs independently on its own PC. Both need internet and your private relay.

Previously **Codaki Mini Codex**. Version 0.3.0 adds autonomous original Codex to the existing device agent. Existing ZIP names, module IDs, tool names, credentials and installation paths retain their legacy names for compatibility.

## What is it for?

Use RelayKite when you want a conversation to lead to an action on your own device:

| You ask | The device agent can do |
| --- | --- |
| “Check my phone's battery and available storage.” | Return device status and inspect storage through available tools. |
| “Open Settings and tell me what is on the screen.” | Launch the app, read the UI or capture a screenshot. |
| “Save this note in my chosen folder.” | Write a file within the configured access. |
| “Diagnose why my phone agent stopped.” | Inspect relevant services and reuse saved maintenance notes. |
| “List large files in this Windows folder.” | Run an authorized PowerShell task on the connected PC. |

These are example requests, not recorded demos. Actual results depend on your device, configured permissions and available tools.

## Choose your device

| | Android | Windows |
| --- | --- | --- |
| Local worker | APK-embedded Bionic Python/Node | Python background agent + PowerShell |
| Requirements | Android app; existing Magisk for root modes; Termux optional | Python 3.14+, PowerShell and selected permissions |
| Connection | Your authenticated HTTPS MCP relay and supported ChatGPT plugin | Your authenticated HTTPS MCP relay and supported ChatGPT plugin |
| Does it need the other device? | No permanently running PC after setup | No phone required |
| Install | Signed APK; matching Magisk ZIP for root modes | `mini-codex-pc-0.3.0.zip` |
| Guide | [Android installation](docs/install-android.md) | [Windows installation](pc/README.en.md) |

## How it works

```text
You → ChatGPT → your personal plugin → your private HTTPS relay
                                                ↕
                                    Local device agent
                                    Android or Windows
                                                ↓
                                    Action → result → chat
```

The model runs in ChatGPT. Ordinary device tools return their result to the conversation; autonomous development adds an on-device Codex supervisor that requests further model decisions through a saved conversation after the outer response ends. RelayKite does not host model weights or remove account limits. Memory stores notes and verified solutions between tasks; it does not train model weights. [Architecture and private relay setup](docs/deploy-private-relay.md).

## Get started

1. **Check the requirements.** Autonomous Android development needs existing root/Magisk, the signed runtime and the Portable component; Termux is optional; Windows needs Python 3.14+ and PowerShell. Check that your ChatGPT account supports the required personal plugin connection.
2. **Download the right installer and `SHA256SUMS`** from [release v0.3.0](https://github.com/Stervakim/relaykite/releases/tag/v0.3.0). Check the SHA-256 checksum before installation.
3. **Follow the guide for your device.** Configure your own private relay and credentials, then connect your personal plugin. Importing a public card alone does not connect your device.
4. **Verify with a small task.** Start with device status, inspect a test app or list a test folder, and check the actual result.

For assisted installation, give Codex the release ZIP and checksum file:

> Install RelayKite v0.3.0 from this ZIP on my chosen device. Read INSTALL_WITH_CODEX.md, verify SHA256SUMS and requirements, configure my own private relay, and verify the connection. Use the device tools available to you. Preserve existing credentials, pairings, permissions, memory and logs during an update.

Initial Android preparation may need a computer. The installer does not install root or enable unavailable account features. [Compatibility](docs/compatibility.md) · [Access and data](docs/security.md).

## Release 0.3.0

Original Codex 0.154.0 runs on the phone with native patches, shell, Git and semantic Android MCP tools. A durable supervisor continues a task after the outer ChatGPT answer, records checkpoints and receipts, and supports pause, resume and cancellation. Model requests use a normal saved ChatGPT conversation; no API key or temporary chat is required for this transport. The installed ChatGPT app, an unlocked device, network access and account capacity remain necessary.

Context is bounded and can use original Codex compaction. Compatible Codex skills and configured MCP servers can be used; ChatGPT plugins do not automatically become Codex tools. Android root execution is unsandboxed. Native Android model image input is disabled in this release. [Architecture and operation](docs/DEVELOPMENT.md) · [Verification and limits](docs/development-progress.md).

[Changelog](CHANGELOG.md) · [Boot and proxy guide](docs/resilient-boot.md) · [Optional memory runtime](agent/memory-runtime/README.md) · [Portable session instructions](chatgpt/plugin/skills/using-codaki-phone-use/SKILL.md)

## Learn, verify and contribute

- [Control Android from ChatGPT without a running PC](https://stervakim.github.io/relaykite/guides/android-without-pc/) — how the architecture works and how to check it.
- [Windows guide](pc/README.en.md) — installation, grants and independent operation.
- [Android without a PC: FAQ](docs/pc-free-android.md).
- [Fact sheet for reviewers](docs/press-kit.md) — source-backed claims and a reproducible test plan.
- [Contributing](CONTRIBUTING.md) · [Report a bug](https://github.com/Stervakim/relaykite/issues/new/choose) · [Brand assets](docs/brand.md) · [English launch copy and headline kit](docs/promotion-kit.md).

Version 0.3.0 was exercised on Redmi Turbo 3 / Android 17 / Magisk using embedded Python/Node, without a Termux runtime. Host/mock checks complement real Codex patch, shell, Git, compaction and Android MCP acceptance; other devices still require testing. Android virtual-display support depends on separately installed components. Do not assume offline AI, lock-screen bypass or identical support on every device.

[Codaki Android Use](https://github.com/Stervakim/codaki-android-use) and [Codaki Portable Use](https://github.com/Stervakim/codaki-portable-use) are separate companion repositories.

## License and support

RelayKite is an independent open-source project under the [MIT license](LICENSE). It is not an official OpenAI product. Source and public releases are free; your ChatGPT account and relay hosting may have their own costs. [Support development on Boosty](https://boosty.to/mini_codexandroid).
