# RelayKite: Android phone control with no PC at runtime

RelayKite is built to run its command execution worker on Android itself, rather than on a connected computer.

## Does it need a PC to work?

**No.** After the owner's rooted Android device, private relay and personal ChatGPT plugin have been configured, normal command execution does not require a laptop, desktop, USB cable, desktop ADB, scrcpy or a continuously powered-on computer.

**It does need:** the powered-on Android phone with Magisk root and Termux, internet connectivity, the private HTTPS relay, and access to the owner's supported ChatGPT plugin.

## How does background operation work?

The Magisk late-start script starts a Python worker on the phone after boot. The worker makes authenticated outbound HTTPS requests to its private relay, retrieves pending authorized tasks and executes them locally. No incoming ADB connection to the phone is needed. Android battery policies, unavailable internet/relay or the first unlock needed for encrypted storage can stop or delay work. This is independent of a PC but not guaranteed uninterrupted execution under every lock state.

## What can it do?

Depending on permissions and Android behaviour, available tools inspect phone state and battery, take screenshots, read UI elements, perform taps/swipes/keypresses, launch apps, inspect or change files, run root shell commands, download files and install owner-approved APKs. Read [access and data](security.md) before enabling root.

## Is setup also always computer-free?

Not necessarily. Bootloader unlocking and rooting may require a computer depending on the phone. The claim is specifically **PC-free operation after setup**, not PC-free installation on every device.

## What distinguishes RelayKite from other Android Codex projects?

RelayKite focuses on **ChatGPT-to-Android device control with a phone-local, Magisk-started root worker**. It is **not** just a terminal port of Codex CLI or a desktop remote-control client: the agent itself executes tasks directly on Android without a running PC. Its private relay runs online, and the ChatGPT plugin submits jobs to the worker.

This distinguishes the **architecture and purpose**, not an independently verified claim to be the **first or only** Android Codex agent. Other public projects already connect Codex/ChatGPT to Android device tooling; see [android-codex-bridge](https://github.com/tamir-oss/android-codex-bridge). The term "autonomous" here means **computer-independent execution and background polling**, not offline model inference or unsupervised decision-making.

## Can it control a secure locked screen invisibly?

Do not assume so. A secure keyguard may require owner unlocking; isolated/hidden virtual display control is not a verified public-release feature.

## Search terms

Android Codex; ChatGPT Android agent; ChatGPT phone control; control Android from ChatGPT without PC; Android automation no computer; root Android agent; Android phone MCP plugin; Codex on Android.

Independent MIT-licensed project, not an official OpenAI product.
