---
name: calendar
description: Расписание — встречи CalDAV и платежи из финансового календаря одним списком.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [calendar, caldav]
    category: productivity
    related_skills: [desk, mail, finance]
    requires_toolsets: [terminal]
---

# Календарь

```bash
PYTHONPATH=. python3 -m desk calendar
```

В `events` и встречи Яндекса, и платежи с `account: finance`. Событие на весь день — платёж, не созвон в 00:00.

Говори ближайшее впереди: название, день, время или «весь день». Занятое время не забивай новой встречей, пока владелец сам не попросил записать поверх.

Обновить окно с сервера: `POST /api/calendar/refresh` на `ASSISTANT_URL`, если список пуст и `last.errors` не пуст. Пустой список без ошибок значит, что встреч нет.
