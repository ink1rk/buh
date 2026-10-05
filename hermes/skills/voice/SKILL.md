---
name: voice
description: Голос Edge через MCP — озвучить фразу, ключ не нужен.
version: 1.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [voice, edge, tts, mcp]
    category: voice
    related_skills: [telegram]
---

# Голос

Провайдер речи — Edge, голос `ru-RU-DmitryNeural`. Ключ не нужен.

В Telegram голосовые ответы включает сам Hermes (`/voice on` или `/voice tts`). Файл — инструмент `voice_speak` сервера MCP `voice`, когда владелец просит сохранить запись. Если инструмент вернул ошибку, скажи, что голос не собрался, и отдай текст.
