# Codaki — autonomous AI agent for Android (Mini Codex)

![Codaki — Desktop freedom. Android.](docs/assets/codaki-cover.png)

**Mini Codex Android · Миникодекс**

Version0.2.4 adds original Tencent external memory, Graphify code queries and the existing Portable Use IPC bridge. Memory setup is optional and requires Termux Node24; GPT in the active chat supplies summaries. No parallel Android sessions or background LLM are claimed. Runtime provenance and setup: [memory guide](agent/memory-runtime/README.md).

**English** · [Русский](README.ru.md) &nbsp; | &nbsp; **v0.2.4** · [MIT](LICENSE)

**Codaki AI · Mini Codex Android is an AI agent for controlling your phone through ChatGPT.** Launch apps, inspect the screen, manage files and automate tasks on a rooted Android phone. The project is also known as **Codaki ИИ** and **Миникодекс** in Russian.

**Codaki runs on the phone itself, without a permanently running PC.** After setup, normal use requires no USB or desktop ADB connection. You still need internet access, your own private HTTPS server and a ChatGPT plugin supported by your account.

**Desktop freedom. Android.** Codaki aims to bring Codex-like freedom of action to your phone: apps, files and authorized system commands, controlled from an ordinary ChatGPT conversation through your personal plugin.

**Codaki AI on GitHub:** this repository contains **Mini Codex**, the phone-resident agent and private MCP server. [Codaki Android Use](https://github.com/kalabuxova1-hash/codaki-android-use) is a separate companion project for controlling Android from a computer. Here, autonomous operation means running the phone worker without a permanently running PC; ChatGPT supplies the AI decisions.

[Install Codaki](#codaki-install) · [Features](#codaki-features) · [Documentation](#codaki-docs) · [Download release](https://github.com/kalabuxova1-hash/codaki-mini-codex/releases/latest)

<br>

<a name="codaki-features"></a>

**New in 0.2.4:** auto-restart on agent failure, optional validated loopback HTTP proxy for VLESS, single-instance lock, configuration/state preservation. [Boot + proxy guide](docs/resilient-boot.md)

## What Codaki AI can do

<table>
<tr>
<td align="center" valign="top" width="56">
<img src="docs/assets/icons/phone.svg" width="40" height="40" alt="">
</td>
<td valign="top">
<strong>Control Android</strong>
<p>Launch apps, inspect the screen, tap, swipe and check your phone's status.</p>
</td>
</tr>
<tr>
<td align="center" valign="top" width="56">
<img src="docs/assets/icons/files.svg" width="40" height="40" alt="">
</td>
<td valign="top">
<strong>Manage files</strong>
<p>Read, save and download files. Install owner-approved APKs and run authorized local commands.</p>
</td>
</tr>
<tr>
<td align="center" valign="top" width="56">
<img src="docs/assets/icons/memory.svg" width="40" height="40" alt="">
</td>
<td valign="top">
<strong>Remember solutions</strong>
<p>Keep preferences, notes and verified ways to complete tasks. Memory and operational records — up to 5 GiB.</p>
</td>
</tr>
</table>

Codaki AI combines ChatGPT phone control and Android automation: a Python worker in **Termux**, startup through **Magisk** and a private **MCP server (Model Context Protocol)** for the personal ChatGPT plugin. The language model plans tasks; the phone worker executes authorized actions.

<br>

<a name="codaki-install"></a>

## <img src="docs/assets/icons/wrench.svg" width="36" height="36" alt=""> Install Codaki and connect the plugin

### Prepare your phone

- Android with **root and Magisk already installed**. You install root yourself.
- Official [Termux](https://github.com/termux/termux-app/releases) with Python.
- The ability to connect a personal ChatGPT plugin and configure your own private HTTPS server.

### Install with Codex

1. **Download the Codaki release.** Get `mini-codex-magisk-0.2.4.zip` and `SHA256SUMS` from the [latest release](https://github.com/kalabuxova1-hash/codaki-mini-codex/releases/latest).

2. **Give the files to Codex.** Ask it to check requirements, install the module and configure your private server and plugin. A ready-to-use prompt is below.

3. **Check the connection.** Select your personal “Codaki Mini Codex — phone” plugin in ChatGPT and ask: “Check my phone's status.”

**ChatGPT card ZIP:** [download `codaki-mini-codex-chatgpt-0.2.4.zip`](chatgpt/codaki-mini-codex-chatgpt-0.2.4.zip). It is also bundled inside the installer under `chatgpt/`. Import adds the workflows; connect your own phone after installation. The public ZIP has no author-specific App ID or device pairing. [Connect the card to your own server](chatgpt/README.md).

<details>
<summary><strong>Show the installation prompt for Codex</strong></summary>

> Install Codaki Mini Codex 0.2.4 from this file on my phone. Read INSTALL_WITH_CODEX.md inside the ZIP, verify requirements, configure my own private relay/plugin and check the connection. Use available phone tools or authorized ADB; retain existing settings and memory on upgrade.

If Codex already has an authorized phone-control channel, it can use it. Otherwise connect the phone to the computer running Codex and approve USB debugging. Codex handles the supported installation and configuration steps; Android may require you to unlock after reboot.

The ZIP does not root the phone, install Termux or turn a phone-only chat into an ADB host. The embedded instructions are a workflow for Codex with actual device tools, not an independent installer AI. Firmware, drivers and bootloader unlocking tools are not distributed here.

</details>

### Update with GPT

**A new version is out → download the new ZIP → give the file to GPT → ask it to update the plugin.**

> Update this Codaki plugin from the new ZIP. Keep my phone connection, private server, keys, memory and journal. Check the version and checksum, update the existing card, and verify the connection. If this is the full installer, also update the phone components using INSTALL_WITH_CODEX.md.

The bundled update workflow retains your existing App reference and ChatGPT owner binding. A card-only update leaves the phone runtime unchanged. GPT uses the client's available update/import tools; if the client requires a manual import, it prepares the replacement ZIP and tells you that final step. The file must come from this project's Releases. [Card setup and updates](chatgpt/README.md).

**Initial setup may require a computer.** PC-free operation describes day-to-day use after setup.

[Installation and manual setup](docs/install-android.md) · [Private server setup](docs/deploy-private-relay.md)

The root [`mcp.json`](mcp.json) provides an HTTP endpoint configuration template for the private MCP server. Replace its example URL only in your private copy and follow the [connection and authentication notes](docs/deploy-private-relay.md#mcp-configuration-template).

<br>

<a name="codaki-docs"></a>

## <img src="docs/assets/icons/book.svg" width="36" height="36" alt=""> Codaki documentation

Details are grouped by topic — open the section you need.

<details>
<summary><strong>Ordinary ChatGPT chat, ongoing use and usage costs</strong></summary>

Control the phone through your personal Codaki plugin in a supported ChatGPT chat. Codaki's phone worker executes actions locally; it does not run a second model API session. The supported ChatGPT plugin flow needs no separate OpenAI API key, and Codaki itself adds no per-token fee.

Continue with new tasks and reuse saved solutions between conversations. This is designed for ongoing use after setup, not a guarantee of an infinitely long chat or uninterrupted background work. ChatGPT still uses tokens and context, and your account's [usage limits](https://learn.chatgpt.com/docs/pricing) still apply. Private relay hosting may have its own costs.

The goal is broad phone access comparable in spirit to Codex on a PC. Android permissions, supported tools and device compatibility determine the actual scope; feature parity with desktop Codex is not claimed.

</details>

<details>
<summary><strong>How Codaki controls Android without a PC</strong></summary>

A Python worker runs **on the phone itself** in Termux, started by Magisk. It polls the owner's private HTTPS server for authorized jobs and executes them on Android. The computer can be completely powered off during normal operation.

```text
ChatGPT → personal Codaki plugin → private HTTPS server
                                          ↕
                           Android: Codaki + Termux + Magisk
                                          ↓
                           Apps, screen, files and root commands
```

- **Background operation.** Magisk starts the worker after Android boots. Power management or a secure first-unlock requirement may interrupt it.
- **Personal connection.** Each owner needs their own private server, plugin and credentials. The author's personal plugin is not a shared server for other people's phones.
- **Plugin availability.** This depends on your ChatGPT account and must be checked during setup. Installing the ZIP does not enable missing account features.

Codaki is not a fully offline AI: requests require ChatGPT, internet access and a functioning private server. The worker does not bypass a secure lock screen. A hidden virtual display is not a verified public release feature.

[PC-free Android operation FAQ](docs/pc-free-android.md)

</details>

<details>
<summary><strong>Codaki memory and what's new in version 0.2.0</strong></summary>

Memory stores short notes, preferences and compressed archives between tasks. Memory and operational records share a **5 GiB** limit: storage fills gradually, and the oldest records are removed when the limit is reached. Arbitrary downloads and files written by root commands are outside this budget. This stores experience; it does not train model weights.

- A support skill guides diagnosis, service/file discovery and verification after maintenance.
- A local passport records Android version, installed-package metadata, Magisk modules, important paths and a verification timestamp. Each phone generates its own inventory locally; the support guide instructs the agent to refresh it after component changes.
- `phone_status` exposes the guide, summary, freshness flag and refresh command.
- Existing memory retrieves previous confirmed solutions and saves new verified lessons. No second history store or model-weight training is added.
- The 0.2.4 module and ChatGPT card display version 0.2.4; upgrades retain connection settings, memory and the job journal.

[Codaki 0.2.0 changelog](CHANGELOG.md)

</details>

<details>
<summary><strong>Compatibility, verified devices and access</strong></summary>

**Verified personal configuration:** Redmi Turbo 3, Android 16, root, Magisk and Termux. The public v0.2.4 ZIP was checked by host and mocked tests but not installed over the working personal installation. Other devices require separate testing.

To stop control, disable the Codaki Mini Codex module in Magisk. Removing the module preserves memory and configuration. Do not share credentials or access to your personal plugin.

[Android compatibility](docs/compatibility.md) · [Access and data](docs/security.md)

</details>

<details>
<summary><strong>Materials for reviewers and journalists</strong></summary>

Reviewers and journalists can use the [Codaki fact sheet and reproducible PC-free testing checklist](docs/press-kit.md). It distinguishes verified features from author reports and clearly lists limitations and independent testing steps.

The `agent/`, `magisk/` and `relay/` sources are provided for inspection and personal deployment. Users do not need to download the entire repository to their phone.

</details>

<br>

## <img src="docs/assets/icons/heart.svg" width="36" height="36" alt=""> Support Codaki

Voluntary support on [Boosty](https://boosty.to/mini_codexandroid) helps develop Codaki, test compatibility and fix bugs. Source code and public releases remain free under the **MIT license**.

---

**Codaki** is an independent open-source project, not an official OpenAI product or the official Codex CLI. Licensed under [MIT](LICENSE).


## Mini Codex PC 0.2.4 — PowerShell и другие плагины

[Установка через Codex и обновление новым ZIP](pc/README.md) · [Подробная инструкция](pc/INSTALL_WITH_CODEX.md)

Скачайте `mini-codex-pc-0.2.4.zip` и `codaki-mini-codex-pc-chatgpt-0.2.4.zip` из [релиза 0.2.4](https://github.com/kalabuxova1-hash/codaki-mini-codex/releases/tag/v0.2.4). ZIP-карточка также находится внутри установщика. Передайте ZIP и SHA256SUMS Codex и попросите установить по INSTALL_WITH_CODEX.md. Вышла новая версия → дайте ZIP GPT → попросите обновить агент и плагин, сохранив связи, App ID, права, ключи и журнал.

Фоновый Windows-агент без окна выполняет разрешённые команды PowerShell и операции с файлами. Телефон для него не требуется. Телефонный Mini Codex по-прежнему работает без ПК. Оба устройства работают самостоятельно; постоянное соединение между ними не нужно. По запросу можно обратиться к сопряжённому устройству, если оно онлайн.

Количество связей телефон ↔ ПК программно не ограничено. Почта ChatGPT используется для приглашения, а доступ требует входа соответствующего аккаунта, сравнения отпечатка и подтверждения владельца ПК. Каждая связь хранится отдельно, имеет свои права и отзыв. Для разных аккаунтов нужны также штатные разрешения доступа к приватному Site/плагину. Email их не обходит.

GPT может сочетать Mini Codex с доступными Computer Use, Sites и другими плагинами, соблюдая их разрешения и проверяя конкретный ПК/аккаунт. PowerShell-агент не наследует скрытые инструменты этих плагинов. Обычный Codex подключается через явно разрешённый владельцем Codex CLI.
