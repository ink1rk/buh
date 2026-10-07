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
| почта Яндекса | `yandex` | `yandex_recent`, `yandex_move`, `yandex_delete` |
| почта Google | `gmail` | `gmail_recent`, `gmail_move`, `gmail_delete` |
| расписание | `calendar` | `calendar_events`, `calendar_create` |
| заметка | `notes` | `notes_write`, `notes_search` |
| непрочитанное в Telegram | `telegram` | `telegram_unread` |
| сказать вслух | `voice` | `voice_speak` |
| страница в браузере | — | навык `browser` |

Финансы отдельным MCP не подключены: того приложения больше нет. Телефон тоже не подключён: мост не запущен и устройств нет, `phone_*` не вызывай. Не выдумывай письма, встречи и цифры. Если инструмент вернул ошибку — скажи её, не заполняй пробел.
