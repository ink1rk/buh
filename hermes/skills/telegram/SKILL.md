---
name: telegram
description: Telegram владельца — бот Hermes для разговора, каналы и непрочитанное без сбора чужих чатов.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [telegram]
    category: messaging
    related_skills: [desk, voice]
    requires_toolsets: [terminal]
---

# Telegram

Разговор с владельцем идёт через бота Hermes. Чужие личные чаты не забирай и не включай сбор входящих: владелец их видит сам.

Непрочитанное и каналы — у сервиса аккаунта:

```bash
PYTHONPATH=. python3 -m desk telegram
```

Отправку от имени владельца не делай, пока он не сказал, кому и какой текст. Голосовой ответ — навык `voice`, не файл, собранный вручную.
