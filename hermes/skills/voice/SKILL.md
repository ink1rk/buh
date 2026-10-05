---
name: voice
description: Голос ElevenLabs — озвучить ответ, если включён TTS или владелец просит сказать вслух.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [voice, elevenlabs, tts]
    category: voice
    related_skills: [telegram]
---

# Голос

Провайдер речи — ElevenLabs (`tts.provider: elevenlabs`). Ключ и голос только из окружения: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.

В Telegram голосовые ответы включает сам Hermes (`/voice on` или `/voice tts`). Отдельный файл нужен, только если владелец просит сохранить запись:

```bash
PYTHONPATH=. python3 -m desk voice "короткая фраза"
```

Если в ответе `ok: false` — скажи, что голос не настроен, и отдай текст. Не подставляй другой синтез.
