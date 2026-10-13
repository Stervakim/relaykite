# RelayKite: personal phone relay

English | [Русский](README.ru.md)

The relay page uses English by default. Select **Русский** to view it in Russian, or **English** to switch back.

This source template connects one owner's private ChatGPT plugin to one rooted Android phone. Each deployment has its own private Site, database, plugin and phone credential. It is not a shared public control server.

Follow [Deploy your own private relay](../docs/deploy-private-relay.md). The template's hosting manifest intentionally contains no project ID or credentials. Deploy from your own private checkout and leave this public template unchanged.

For local source checks, use Node.js 22.13 or newer:

```sh
npm ci
node --test tests/*.test.mjs
npm run build
```

The build creates Cloudflare-compatible Worker output. Local development uses a mock sign-in identity; that mock does not establish production ownership. The hosted Site must remain private, and Sites must enforce authentication at its boundary.

The source preserves the first authenticated owner pin, token-authenticated phone endpoints, bounded job queue, atomic job claiming, request deduplication and uncertain-result handling. An expired or uncertain job must be checked before repeating a destructive operation.
