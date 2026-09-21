# Диалоги, сообщения и эпизоды

`domain/conversations.py`, `domain/episodes.py`, `domain/enrichment.py`.

## Модель

**Conversation** — переписка с человеком на платформе:
`id`, `platform`, `external_id`, `contact_id`, `title`, `status`, `summary`,
`summary_updated_at`, `last_message_at`. Уникальна по паре
`(platform, external_id)`.

Платформы: `telegram` — переписка с людьми через аккаунт владельца,
`telegram:bot` — диалог владельца с самим ассистентом.

**Message**: `id`, `conversation_id`, `external_id`, `sender_id`,
`sender_type` (`CONTACT` | `OWNER` | `ASSISTANT`), `text`, `message_type`,
`transcription`, `ts`, `reply_to`, `metadata`.

Типы сообщений: `TEXT`, `VOICE`, `IMAGE`, `DOCUMENT`, `VIDEO`, `SYSTEM`.

Запись идемпотентна по `(conversation_id, external_id)`: повторный апдейт
Telegram не создаёт дубликат.

## Голосовые сообщения

```
Telegram voice
   ↓ getFile
   ↓ POST /stt            (faster-whisper на сервере)
   ↓ transcription
Message(message_type="VOICE", transcription="…")
   ↓
обычный пайплайн ядра
   ↓
ТЕКСТОВЫЙ ответ
```

Ассистент никогда не отправляет голос или аудио. В базе остаются и тип
сообщения, и транскрипт, так что история читается целиком.

## Контекст для ответа

В модель не уезжает вся переписка. `ContextResolver` собирает:

* последние 20 сообщений;
* summary диалога;
* релевантную память (см. `docs/memory.md`);
* последние эпизоды;
* открытые обязательства с этим человеком;
* наблюдаемый стиль общения.

## Summary

Обновляется асинхронно: не чаще чем раз в `SUMMARY_MIN_AGE` (10 минут) или
каждые `SUMMARY_EVERY` (6) сообщений. Формат — structured output
`ConversationSummary`: summary, title, decisions, entities.

Пример:

> Обсуждение настройки сервера X. Система успешно настроена.
> title: «Настройка сервера X», decisions: [«Сервер X настроен»],
> entities: [«сервер X»]

## Эпизоды

Эпизод — законченный фрагмент общения. Новый начинается, если пауза превысила
`GAP` (3 часа), иначе дополняется текущий.

Поля: `title`, `summary`, `decisions`, `commitments`, `entities`,
`started_at`, `ended_at`, `contact_id`, `conversation_id`.

Это то, что отвечает на «что мы с Иваном решили по серверу»: не поиск по
сообщениям, а конкретный эпизод с решениями.

## Фоновая обработка

`Enricher.on_message()` запускает отдельный поток — пользователь не ждёт:

1. извлечение памяти;
2. извлечение обязательств (и закрытие ожиданий, если человек ответил);
3. обновление summary и эпизода;
4. пересчёт стиля общения.

Каждый шаг изолирован: падение одного не отменяет остальные, а недоступность
модели вообще не влияет на чат.

## Приватность

```
DELETE /api/conversations/{id}    удаляет диалог вместе с сообщениями
DELETE /api/memory/{id}           удаляет запись памяти физически
DELETE /api/contacts/{id}         удаляет контакт
```

## API

```
GET    /api/conversations                      список с summary и контактом
GET    /api/conversations/{id}                 диалог + эпизоды
GET    /api/conversations/{id}/messages
DELETE /api/conversations/{id}
GET    /api/episodes?contact_id=…|conversation_id=…
POST   /api/ingest/telegram                    входящее сообщение от tg-user
```
