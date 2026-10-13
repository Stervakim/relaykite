# Изменения

## 0.2.4 — Tencent memory and Graphify

Оригинальное хранилище Tencent в режиме external и чтение графа оригинальным Graphify. Метаданные источника/статуса/устройства/проекта/версии, полное чтение и ограниченный поиск. Необязательная установка памяти требует Node.js в Termux. IPC-мост к существующему Portable Use поддерживает 12 операций движка; параллельные Android-сессии и фоновая LLM пока не реализованы. Сохранены проверенное поведение доставки/метрик, восстановление службы памяти и личная конфигурация.

Обновление: 12 инструментов `phone_use_*` используют существующий Android-движок Portable с устойчивыми ID запросов и скриншотами в формате MCP. `phone_job_cancel` отменяет только задания владельца в очереди. Добавлены инструкции по сессиям и проверке неопределённого результата. Нужен установленный Portable; параллельные Android-сессии, Windows Portable IPC и управляемые терминалы пока не добавлены.

Windows: 12 операций pc_use_* используют существующий Portable0.1.3 через локальный RPC под уже одобренной capability terminal. Добавлены Windows batch, native images и отмена только PC-заданий в очереди. Нужен --local-ipc-windows. Оконные сессии разделяют рабочий стол; физический ввод остаётся последовательным.

## 0.2.3 — Mini Codex PC

Включает функции 0.2.2: локальный прокси Shadow VLESS и автоперезапуск Android-агента после сбоя. Сохраняются настройки прокси, enabled, ключи, память и журнал.

Исправлена доставка результатов при другом Android VPN: агент учитывает режим ожидания Shadow VLESS и автоматически возвращается к заданному прокси после его завершения. Настройки сети не меняются. Исправлено чтение SID Windows при русской кодировке системного вывода.

- Windows background agent: PowerShell, files, durable no-replay journal, local consent and revocation.
- Saved email-addressed pairing with ChatGPT sign-in and PC fingerprint approval; no fixed link-count limit.
- Independent phone/PC use, optional two-way requests, PC-only operation.
- Separate PC installer and portable GPT card; Codex installation and App-preserving ZIP update workflows.
- Composition with available, owner-authorized Computer Use/Sites client plugins; optional installed Codex CLI.
- Additive PC relay migration; existing phone owner pin and private runtime preserved.

[English](CHANGELOG.md) | Русский

## 0.2.2

Объединены преимущества личной Android-сборки и публичного релиза: автоперезапуск Magisk-службой после неожиданного завершения агента с паузой 15 секунд, работа через добровольно указанный локальный HTTP-прокси (127.0.0.1 или ::1, пригоден для теневого VLESS), существующая блокировка второго агента, проверка конфигурации, сохранение памяти, журнала и приватного relay.

Ни подписка VLESS, ни ключи, ни URL личного сервера не включены в GitHub/ZIP. Для старой личной установки с прокси в service.sh требуется безопасный перенос адреса прокси и маркера enabled; установка 0.2.2 на телефон автора не заявляется. Инструкция: docs/resilient-boot.ru.md.

## 0.2.1

Includes an update skill: give GPT a newer ZIP to prepare/apply an update while preserving the existing App reference, private relay and phone state.

Packaging update: include the portable ChatGPT card ZIP, icon, setup/control skills and card builder inside the Magisk installer and as a separate release download. Public cards have no owner App ID or device pairing; an owner-specific App reference can be built privately after relay setup. Checksums cover both archives. The phone runtime and module remain 0.2.0; no device code or existing owner configuration changes.

## 0.2.0

Основной способ установки — передать ZIP в Codex. В архив включён `INSTALL_WITH_CODEX.md`: работа через доступный канал устройства или ADB, настройка собственного приватного relay и проверка связи. Нужны реальные инструменты управления и заранее установленные root/Magisk/Termux с Python; это не отдельный автономный AI-установщик.

Версия Codaki Mini Codex 0.2.0 добавляет встроенную поддержку устройства. `phone_status` возвращает навык, паспорт с датой проверки, пути справочников и команду обновления. Паспорт создаётся на телефоне каждого владельца из свойств Android, метаданных пакетов и Magisk-модулей и наличия путей. Личный паспорт автора в выпуск не включён.


Навык использует существующие заметки и журнал заданий: ищет прошлые решения и сохраняет подтверждённый опыт обслуживания. Веса модели не обучаются, дополнительная AI-модель не запускается. После проверки настройки служба Magisk обновляет паспорт; ошибка обновления не мешает запуску агента. При обновлении сохраняются секреты подключения, память и журнал.

В панели и Magisk отображается 0.2.0, в пакетах и MCP — `0.2.0`. Пути публичной сборки отличаются от существующей личной установки автора. Публичному ZIP нужен собственный приватный relay.

## 0.1.0

Первый публичный комплект: Python агент на Android, Magisk установщик, локальная настройка секретов и шаблон отдельного приватного Site relay.

Добавлены ограниченная память с gzip архивами, журнал заданий, проверки установки и сканер содержимого выпуска. Публичный комплект не содержит личной конфигурации и не обновляет работающие установки автоматически.
