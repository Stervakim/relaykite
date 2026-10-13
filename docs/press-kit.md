# RelayKite for Android — facts for independent reviewers

> This document is authored by the project team. It is a **primary source**, not an independent review or evidence of Wikipedia notability.

## Project summary

**RelayKite** is an independent open-source project for controlling the owner's Android phone from a personal ChatGPT plugin. Commands execute **on the Android phone itself**, not on a connected desktop. After setup, normal operation does not require a running PC, USB, desktop ADB or scrcpy. **Not an official OpenAI product.**

Repository: https://github.com/kalabuxova1-hash/relaykite

Release: https://github.com/kalabuxova1-hash/relaykite/releases/latest

License: MIT.

## Architecture

1. The owner requests an action through ChatGPT and a **personal plugin**.
2. A private HTTPS relay receives the authorized task.
3. The on-phone agent polls the relay for a job.
4. Termux/Magisk execute the action locally; the agent returns the result.

**No-PC operation refers to task execution after setup.** Bootloader unlocking and initial rooting may require a computer on some phones. Internet access, the private relay, ChatGPT plugin access, and a running Android agent are still needed.

## Code-level features

- Phone/battery status; screenshots and UI hierarchy; taps, swipes, keys, app launching.
- File listing, reading, writing, HTTPS downloads and owner-approved APK installation.
- Android-local root shell execution.
- Magisk background startup and task journal.
- Short local notes with managed 5 GiB storage budget.
- Private per-owner relay credentials and separate plugin authorization.

See [Android installation](install-android.md), [private relay](deploy-private-relay.md), [security](security.md) and [PC-free operation](pc-free-android.md).

## Suggested independent verification (not a claim of completed testing)

1. Prepare a test Android phone with Magisk/Termux, a separate private relay and plugin.
2. Verify device identity and root.
3. Completely power off the PC and unplug USB.
4. Send safe commands from ChatGPT: phone status, app launch, UI inspection and temporary file write.
5. Repeat after reboot/first unlock and with screen off, new network, and different background power policies.
6. Revoke relay credentials and verify old credentials no longer work.

**Current scope:** author's personal use on Redmi Turbo 3 / Android 16 / root. The public v0.2.0 ZIP passed host/mock checks, not a full deployment over the author's working installation. Other devices need independent testing.

Independent critical reviews are welcome; editorial independence and reporting of negative outcomes must be respected. The repository, its press materials and reposts are not independent sources for encyclopedic notability. No unverified world's-first/only claim is made.
