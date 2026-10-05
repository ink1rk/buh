---
name: desk
description: Стол владельца — какой модуль звать для почты, календаря, заметок, браузера, Telegram и голоса.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [desk, router]
    category: productivity
    requires_toolsets: [terminal]
---

# Стол

Hermes разговаривает. Данные живут в сервисах рядом. Не выдумывай письма, встречи и цифры.

Из каталога `hermes/` (или `/opt/assistant/hermes`):

```bash
PYTHONPATH=. python3 -m desk modules
```

| Просьба | Команда |
|---|---|
| почта | `python3 -m desk mail` |
| расписание | `python3 -m desk calendar` |
| запомнить, заметка | `python3 -m desk note "заголовок" "текст"` |
| найти в заметках | `python3 -m desk search "фраза"` |
| непрочитанное в Telegram | `python3 -m desk telegram` |
| сказать вслух | `python3 -m desk voice "текст"` |
| страница в браузере | навык `browser` |

Отвечай по JSON. Если `ok` ложно или сервис недоступен — скажи это, не заполняй пробел догадкой.
