# Codaki Mini Codex — телефон: ChatGPT card

The ZIP in this folder contains a manifest, icon, setup skill and phone workflow. The public card has an empty App mapping. Importing it adds the workflow; it does not connect a phone or grant access to the author's server. After setup, the existing server pins the authenticated ChatGPT owner and the phone uses its individual agent token.

Use the plugin archive import provided by your ChatGPT client/workspace, when available. A ZIP attached to an ordinary conversation is not an installed plugin. For local Codex testing, use the included plugin folder in a local marketplace. Availability of import and connection features depends on the account.

For a connected card, use the App ID returned by **your own** private Sites deployment:

```sh
python chatgpt/package_card.py --app-id YOUR_REGISTERED_APP_ID
```

The output is in ignored `.private/chatgpt/`. A registered App ID begins with `asdk_app_`, `connector_` or `templated_apps_`; a `plugin_...` identifier is not an App ID. This only changes the card's App reference. It does not alter the phone, owner pin or agent credentials. Keep the resulting owner-specific card private. The existing Sites card can also be used directly.

## Русский

Публичный ZIP устанавливает карточку с инструкциями настройки и работы. В нём нет ID личного сервера автора, ключей или привязки к устройству. Импорт карточки и подключение телефона — отдельные шаги. После настройки сервер использует ID аккаунта ChatGPT владельца, а телефон — свой токен. Доступ к GitHub не является привязкой телефона.

Для карточки с подключёнными инструментами выполните команду выше с App ID своего приватного сервера. ID позволяет карточке ссылаться на App, но не привязывает телефон. Персональный архив сохраняется в `.private/chatgpt/`; не публикуйте его. Возможность импорта ZIP и подключения зависит от аккаунта и клиента ChatGPT.

Source: https://github.com/kalabuxova1-hash/codaki-mini-codex
Format: https://developers.openai.com/plugins/build/plugins

## Update from a new file / Обновление по новому файлу

Give GPT the newer card ZIP or full installer and ask: «Обнови этот плагин, сохрани подключение моего телефона, ключи и память». The bundled update skill checks the release and retains the current App reference. Build a replacement from the new source with `python chatgpt/package_card.py --previous-card /path/to/current-private-card.zip`. Use the client's supported update/import operation for the existing card. Local rebuilding alone does not update an installed plugin; if the client offers no update tool, GPT prepares the replacement and reports the required import step.
