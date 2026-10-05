---
name: calendar
description: Расписание CalDAV через MCP — Яндекс и Google, если Google подключён.
version: 1.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [calendar, caldav, mcp]
    category: productivity
    related_skills: [desk, mail]
---

# Календарь

Сервер MCP `calendar`.

- `calendar_status` — какие календари живы. Google отмечен отдельно: пароль IMAP Gmail его не открывает.
- `calendar_events` — встречи на ближайшие дни.
- `calendar_create` — записать встречу, когда владелец просит.

Событие на весь день — не созвон в 00:00. Занятое время не забивай новой встречей, пока владелец сам не попросил записать поверх. Пустой список без ошибки значит, что встреч нет.
