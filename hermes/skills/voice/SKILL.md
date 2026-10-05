---
name: voice
description: Голос Edge — озвучить ответ, если включён TTS или владелец просит сказать вслух.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [voice, edge, tts]
    category: voice
    related_skills: [telegram]
---

# Голос

Провайдер речи — Edge (`tts.provider: edge`), голос `ru-RU-DmitryNeural`. Ключ не нужен.

В Telegram голосовые ответы включает сам Hermes (`/voice on` или `/voice tts`). Отдельный файл нужен, только если владелец просит сохранить запись:

```bash
PYTHONPATH=. python3 -m desk voice "короткая фраза"
```

Если в ответе `ok: false` — скажи, что голос не собрался, и отдай текст.
