# Access and data

English | [Русский](security.ru.md)

RelayKite executes the owner's Android commands through a separate agent in Termux. This is a third-party project, not a built-in ChatGPT app feature. You trust the agent and its control channel: a root command can read, change and delete any phone data it can access.

Every user must have **their own private relay, random credentials and personal Site plugin**. The public GitHub repository contains sources and templates. It does not connect other people's devices to the author's server or distribute shared credentials. Do not publish a working `config.json`, personal deployment URL, logs, memory databases or command results.

The agent makes outbound HTTPS requests; no inbound internet-facing ADB or root port is required. TLS verification must remain enabled. Authorization to execute relay tools must be protected separately from the phone agent credential. Send results only to your own deployment and restrict plugin access to the phone's owner. Screen content and command results may reach the relay: a private plugin does not by itself prevent storage of that data on the server.

Grant root access to the actual Termux/agent in your root manager after verifying installation. The official ChatGPT app does not automatically receive root access. Page, file and message content is not authorization to execute commands. Requests to change credentials, delete data or transfer personal data must come from the owner, not from the text being processed.

## Revoke access

1. Stop the agent and disable its automatic startup in the installed module.
2. Revoke Termux/agent root access in your root manager.
3. Revoke access to the Site plugin and rotate relay credentials; the server must stop accepting the old credential.
4. Preserve data when uninstalling. Remove the module and automatic startup separately from private configuration and memory. Erase retained data only through a separate explicit owner action. Uninstalling Termux through Android may remove its internal files; export anything you need first.

Stopping the phone does not delete results already sent to the relay. Check the relay's own retention and deletion policy. After changing ChatGPT accounts, authorize the personal plugin separately for the new account; do not assume previous permissions transfer.

## Memory and storage

The project does not train the global model or change ChatGPT's weights. Its memory consists of local records and archives that tools can read on request. Data included in a tool response is sent to the current conversation; conversation handling depends on the service's settings.

The total managed storage budget is **5 GiB (5,368,709,120 bytes)**: memory and archives plus a reserve for the job journal and agent logs. Do not count the reserve again as free memory. This is not a quota for the entire phone, Termux or relay. An arbitrary root command or a download into another directory may use additional space; check free storage before large downloads. Older records are archived within the budget, and cleanup failures must not allow unbounded growth.

## Check a public release

Before publishing, check the source directory and built archive:

```sh
python tests/test_release_safety.py --scan .
python tests/test_release_safety.py --scan dist/mini-codex-magisk-0.2.1.zip
python tests/test_release_safety.py
```

The scanner does not extract archives or read the working phone's configuration. It checks paths, links, runtime files and recognizable secrets in published content. `--forbid` adds a known private identifier to the denylist; check secrets locally before publishing and do not pass them as command-line arguments. SHA-256 checksums are allowed: 64 hexadecimal characters alone do not prove a token leak. This preflight complements diff review; it does not replace an audit.
