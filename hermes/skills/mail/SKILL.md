---
name: mail
description: Почта Яндекса и Gmail — что пришло, живы ли ящики.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [email, mail]
    category: productivity
    related_skills: [desk, calendar]
    requires_toolsets: [terminal]
---

# Почта

Ящики уже опрашиваются ассистентом. Не подключай IMAP сам и не проси пароль.

```bash
PYTHONPATH=. python3 -m desk mail
```

Смотри `accounts`, `last.new`, `last.financial`, `last.errors`.

- Письмо от человека — скажи, от кого и о чём, если это есть в ответе.
- Чек и счёт (`last.financial`) — это не переписка. Скажи, от кого письмо и какая сумма, если она есть в ответе. Операцию из чека не заводи.
- Отправку письма не делай из этого навыка. Если владелец просит ответить — подготовь текст и жди явного «отправь».
