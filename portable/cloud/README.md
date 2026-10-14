# Codaki Portable Use cloud plugin

Private Sites MCP relay for the installed Android/Windows agent. Preserve owner-only sharing. The Sites gateway authenticates visitors; tools additionally pin the verified owner email. Device requests require both Sites service access and a separate per-device credential. Secrets: OWNER_EMAIL, DEVICE_TOKENS. No credentials belong in this source.

Windows enrollment uses WINDOWS_DEVICE_ID and the separate secret WINDOWS_DEVICE_TOKEN. These extend DEVICE_TOKENS without replacing existing Android credentials. An ID already in DEVICE_TOKENS keeps its original credential.

The worker reuses the Portable Use relay, with embedded tool schemas and Sites authentication. Queue and receipt tables are created with bounded idempotent statements; they are not migration-owned. Session leases, stale-observation refusal, request ID deduplication and result reconciliation are enforced by the device engine.

Build: `node scripts/build.mjs`. Test: `node --test tests/sites.test.mjs`. Publish with the Sites source workflow. The platform provisions the canonical account plugin; never create a second wrapper plugin.

Copy `.openai/hosting.json.example` to `.openai/hosting.json` and use the exact ID of your own Site. Set OWNER_EMAIL and DEVICE_TOKENS as secrets. For an additional Windows PC, set WINDOWS_DEVICE_ID and the independent secret WINDOWS_DEVICE_TOKEN. Preserve the existing Android secret and Site audience. Re-deploy a saved version after environment changes.
