---
name: desk
description: Стол владельца — MCP почты, календаря, заметок, Telegram и голоса.
version: 1.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [desk, router, mcp]
    category: productivity
---

# Стол

Hermes разговаривает. Дела делаются инструментами MCP на этой же машине, не пересказом того, что «нельзя».

| Просьба | Сервер MCP | Инструмент |
|---|---|---|
| почта Яндекса | `yandex` | `yandex_recent`, `yandex_create_sender_folders` |
| почта Google | `gmail` | `gmail_recent`, `gmail_create_sender_folders` |
| расписание | `calendar` | `calendar_events`, `calendar_create` |
| заметка | `notes` | `notes_write`, `notes_search` |
| непрочитанное в Telegram | `telegram` | `telegram_unread` |
| сказать вслух | `voice` | `voice_speak` |
| телефон | `phone` | `phone_today` |
| страница в браузере | — | навык `browser` |

Финансы отдельным MCP не подключены: того приложения больше нет. Не выдумывай письма, встречи и цифры. Если инструмент вернул ошибку — скажи её, не заполняй пробел.
