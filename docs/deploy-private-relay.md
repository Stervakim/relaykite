# Deploy your own private relay

English | [Русский](deploy-private-relay.ru.md)

The public repository contains source code. It does not provide access to anyone else's phone, account, server or plugin. Each owner creates **their own new private Site**, D1 database, phone token and personal plugin. Each instance is intended for one owner and one phone.

## Ask your Codex to prepare the server

Clone the sources into a personal working directory. Deploy a separate private copy of `relay/`: after registration, its hosting manifest will contain your personal ID. Do not push that copy back to the public repository.

You can give your Codex this prompt:

> Use the Sites building, Sites hosting and Sites MCP skills. Deploy the relay sources from this repository as my new owner-private Site with D1 DB and MCP. Do not use any existing Site, project ID, URL, plugin or token belonging to someone else. Preserve the owner pin and queue authorization. Create a separate random phone token, set it as the PHONE_AGENT_TOKEN secret, and prepare my phone configuration outside the repository. Obtain my own Sites bypass for the phone agent. Connect the personal plugin automatically created by Sites for my Site. Check phone_status after connecting my phone.

`relay/.openai/hosting.json` already specifies `d1: "DB"`, `r2: null` and `capabilities: ["mcp"]`. The template intentionally has no `project_id`. Codex must register a **new** Site under your account and obtain its ID and URL from native Sites tools. Configure resources, migrations and hosting through the standard Sites workflow, rather than copying someone else's Cloudflare bindings.

The Site must remain private. Sites enforces ChatGPT authorization at the hosting boundary; public hosting or a manually supplied identity header does not replace that protection. The owner pin binds to the first authenticated owner. Open your own page under your own account first and do not grant others access. Do not clear the owner pin to fix a sign-in error.

## Create a separate phone secret

Use a cryptographic generator: Python's `secrets.token_hex(32)` or Node.js's `randomBytes(32).toString("hex")` produces 64 hexadecimal characters. Generate and store the value locally outside the repository; do not expose it in a shared chat, logs, process arguments or GitHub. Each personal Site needs a new secret.

Use the standard `sites_update_environment_variables` tool to set **secret** `PHONE_AGENT_TOKEN` for your new Site. Follow the current tool schema from the installed Sites plugin. Do not store the working value in the hosting manifest, `.env.example`, sources or public documentation. The example environment file contains only an empty placeholder for local development.

Use the standard `sites_generate_siwc_bypass_token` tool to obtain service authorization **for your own Site**. This lets the phone agent pass the private Sites boundary; it does not establish owner identity for `/mcp` calls or replace `PHONE_AGENT_TOKEN`. Save the issued secret only in your private phone configuration. Respect its expiry and renew it when required by the tool. Do not use another owner's bypass or credential.

## Configure the agent on your phone

Install a module you built yourself or a verified release on **your own** Android with Magisk/root. Use `magisk/configure.sh` and `agent/configure.py` from the same version: they import personal data locally, validate its format and do not print secrets. The archive contains no ready-made configuration and must not automatically bind a phone to the author's server.

Transfer the configuration outside the Git repository. Fields:

| Field | Your value |
| --- | --- |
| `relay_url` | Your new Site's HTTPS URL, without userinfo, query or fragment |
| `agent_token` | The same personal secret set as `PHONE_AGENT_TOKEN` on your Site |
| `sites_authorization` | `Bearer ` followed by your own Sites bypass; an empty string if the chosen hosting does not require it |

```sh
su -c '/data/adb/modules/mini_codex/configure.sh --import /storage/emulated/0/Download/my-relay.json'
```

There is no separate `device_id`. Use one phone and one secret per personal instance. Do not transfer a working configuration between owners. The agent must store its configuration only in a private root directory; check permissions after import. If a credential leaks, rotate the server's `PHONE_AGENT_TOKEN` and the phone's `agent_token` together.

## Connect your plugin and verify

Use the App and personal plugin that Sites creates for **your own** new Site. Codex obtains the connection through `sites_get_site` with `include_mcp_connection: true` and presents a native plugin installation suggestion. Do not create another plugin on top of it or copy someone else's plugin ID. If installation is already available, open Plugins → Personal → Created by you and select your instance.

After starting the agent, check `phone_status`, followed by a fresh `read_ui` or `screenshot`. Confirm that the returned phone is yours and root access is available. Separately verify rejection of incorrect or missing tokens on agent endpoints and denial of access to another ChatGPT owner. When a command returns pending/uncertain, check its `phone_job_result` and the phone's state; do not blindly repeat an irreversible command.

After verification, the agent does not need a computer: the phone polls your personal relay over HTTPS. Internet, a working root environment and the agent service must remain available. Check personal plugin availability in your specific mobile client after connection; these sources do not promise support for every ChatGPT version.

<a name="mcp-configuration-template"></a>

## RelayKite MCP configuration template

The root [`mcp.json`](../mcp.json) describes the relay's `/mcp` HTTP endpoint using the `servers` configuration format documented by [VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers). Its `.example` URL is a placeholder, not a hosted service. The root file is a reference template; it is not automatically loaded as a ChatGPT plugin. Clients use different configuration locations and formats.

Replace the URL with your own private relay's HTTPS URL ending in `/mcp` only in a private copy. The supported ChatGPT connection remains the personal plugin created by Sites, as described above. Keep Sites authentication and the owner pin in place. `PHONE_AGENT_TOKEN` and the phone's Sites bypass are for the phone worker; neither authenticates an MCP client as the ChatGPT owner. Do not put those secrets in `mcp.json` or GitHub.

The endpoint template does not establish compatibility or authentication with other MCP clients; those require separate verification. It is not a legacy `ai-plugin.json` manifest or an MCP Registry submission, and its presence does not guarantee search or AI-crawler indexing.

## Check sources before deployment

Requires Node.js 22.13 or newer. From the `relay` directory:

```sh
npm ci
node --test tests/*.test.mjs
npm run build
```

The template test checks for populated Site IDs, personal hosted URLs, Windows profile paths, predefined device IDs and tokens. Run it **before** personal registration, while the manifest is still a public template. After registration, your private copy will naturally contain your own `project_id`.

Licenses for the vendored build plugin and CSS are preserved. The lockfile pins dependencies. Template checks and a build do not prove that every root command works on every Android device: test your own device separately after deployment.

Auth/queue tests run the actual relay logic with in-memory SQLite, replacing only runtime bindings. They check rejection of missing/incorrect tokens, first-owner pinning, single job claiming under concurrent polling, result persistence, deduplication and transition of expired jobs to `uncertain`. These are local checks; they do not replace private Site authorization at the Sites boundary.
