# Личный ассистент («Джарвис»)

Код сервисов ассистента, который живёт на VM в `/opt/assistant`. Этот каталог —
версионируемая копия: правим здесь, копируем на хост, перезапускаем systemd.

## Состав

| Файл | Что делает |
| --- | --- |
| `core/` | платформа: шина событий, движок действий, разрешения, уведомления, LLM-абстракция, контекст, аудит, интеграции, Core API |
| `domain/` | предметная область: контакты, диалоги, память, эпизоды, обязательства, фоновое обогащение |
| `agents/` | агенты: `personal` (навыки) и `communication` (переписка и подсказки ответов) |
| `providers/` | выход во внешние сервисы: Telegram, почта, инструменты MCP |
| `assistant.py` | приложение FastAPI на `:8800`: навыки (погода, финансы, новости, брифинг), промпт, монтирование Core API |
| `news.py` | сбор и компоновка новостей: 8 лент, дедупликация, темы, рендер в HTML/текст/голос |
| `tgfmt.py` | приведение ответов модели к Telegram-HTML (и обратно — в чистый текст) |
| `tg_bot.py` | Telegram-канал: команды, inline-кнопки, голосовые (только на вход), расписание брифингов |
| `tests/` | офлайн-тесты: ядро, память, контакты, диалоги, обязательства, пайплайн, форматтер |

Рядом на хосте: `tg_user_service.py` (личный аккаунт через Telethon, `:8810`),
мост с телефоном `phone/` (`:8820`, подключается по MCP), `cursor-gateway`
(`:8791`), `ollama` (`:11434`), приложение финансов (`nginx :80`).

## Как новости собираются

1. **Сбор.** Ленты тянутся параллельно; для каждого хоста запоминается рабочий
   маршрут (напрямую или через прокси пользователя), поэтому повторные обходы
   быстрые. Ленты и их темы настраиваются через `NEWS_FEEDS`
   (`Название|url` или `Название|url|тема`).
2. **Фильтр шума.** Выбрасываются рубрики вроде «Из жизни»/«Стиль» и заголовки
   в духе «показала фигуру», «гороскоп», «на правах рекламы»
   (`NEWS_SKIP_CATEGORIES`, `NEWS_JUNK_EXTRA`).
3. **Дедупликация.** Похожие заголовки из разных изданий склеиваются в одну
   новость со списком источников — такие новости помечаются 🔸 и поднимаются в
   «Главное».
4. **Темы.** Сначала рубрика RSS, потом путь ссылки, потом ключевые слова по
   заголовку (сводка используется только как подсказка).
5. **Ранжирование.** Больше источников и весомые формулировки — выше;
   «Названы…», «Раскрыл…» и прочий клик-бейт опускается.
6. **Компоновка.** Блок «Главное» + разделы по темам, не больше N на тему и с
   ограничением на одно издание, чтобы лента не превращалась в один ТАСС.
7. **Рендер.** `render_html` (Telegram: заголовок-ссылка + источники + свежесть),
   `render_flat` (плоский топ для брифинга), `render_text`, `render_voice`,
   `context` (для промпта) и `digest_prompt` (сводка «своими словами»).

Кэш держится тёплым фоновым потоком (`NEWS_CACHE_TTL`, по умолчанию 5 минут),
поэтому `/news` отвечает за миллисекунды, а не за 10 секунд.

## API

Навыки (исторические эндпоинты, продолжают работать):

```
GET  /health                      статус мозгов + статистика новостей
POST /chat                        {text, session, brain, channel}
GET  /news?limit=&topic=&force=   сгруппированные новости: html/text/items
GET  /news/digest?brain=          сводка новостей, собранная моделью
GET  /briefing?evening=&raw=      сводка дня
GET  /weather                     строка погоды + сырые данные
GET  /trading  /channel           сводка и посты Telegram-каналов
POST /stt                         распознавание речи
POST /voice                       голос на вход, текст на выходе
```

Core API — общий для Telegram, Web UI и любого другого интерфейса:

```
POST   /api/chat                          единый пайплайн сообщения
POST   /api/actions                       заявка на действие
POST   /api/actions/{id}/approve|cancel   подтверждение
GET    /api/actions /api/actions/{id}
GET    /api/notifications /api/notifications/pending /api/notifications/digest
POST   /api/notifications/delivered
POST   /api/ingest/telegram               входящее сообщение от tg-user
GET    /api/suggestions/{id}              варианты ответа
POST   /api/suggestions/{id}/send|ignore
GET    /api/memory  POST /api/memory  POST /api/memory/search
GET    /api/memory/{id}  PATCH /api/memory/{id}  DELETE /api/memory/{id}
GET    /api/contacts  /api/contacts/resolve  /api/contacts/{id}
GET    /api/contacts/{id}/context  PATCH|DELETE /api/contacts/{id}
GET    /api/conversations  /api/conversations/{id}  /{id}/messages
GET    /api/commitments  PATCH /api/commitments/{id}
GET    /api/episodes  /api/activity  /api/integrations  /api/permissions  /api/health
GET    /api/mcp                           подключённые серверы MCP и их инструменты
POST   /api/mcp/read                      прочитать данные внешнего сервиса
POST   /api/mcp/call                      вызвать инструмент через движок действий
```

Подробности — в `docs/architecture.md`, `docs/events.md`, `docs/actions.md`,
`docs/permissions.md`, `docs/integrations.md`, `docs/memory.md`,
`docs/contacts.md`, `docs/conversations.md`, `docs/commitments.md`,
`docs/email.md`, `docs/phone.md`.

## Промпт

`build_system(channel, blocks, facts, brain)` собирает системный промпт из частей:
персона → принципы (что делать с данными, когда спрашивать, что подтверждать) →
формат под канал (Telegram-HTML или голос; для локальной 7B-модели формат короче,
она хуже держит длинные инструкции) → список умений → текущие дата/время/город →
факты о пользователе → блок ДАННЫЕ → короткое напоминание в конце.

Роутер: приватные интенты (финансы, переписки, память) уходят в локальную
Ollama, новости и «подумать» — в Cursor-шлюз, остальное — локально. Если один
мозг недоступен, ответ добирается вторым.

## Голос

Голосовые сообщения распознаются (`faster-whisper`) и идут в обычный пайплайн;
ответ всегда текстовый. Синтеза речи в проекте нет — ассистент не отправляет
voice/audio ни в одном сценарии.

## Деплой

```bash
# с машины разработки
tar czf /tmp/core.tgz -C assistant core domain agents providers tests
scp /tmp/core.tgz assistant/{assistant,news,tgfmt,tg_bot,tg_user_service}.py user@host:/tmp/
ssh user@host '
  TS=$(date +%Y%m%d-%H%M%S)
  sudo mkdir -p /opt/assistant/backups/$TS
  sudo cp /opt/assistant/{assistant,tg_bot}.py /opt/assistant/backups/$TS/
  sudo tar xzf /tmp/core.tgz -C /opt/assistant
  for f in news.py tgfmt.py assistant.py tg_bot.py tg_user_service.py; do
    sudo install -o root -g root -m 755 /tmp/$f /opt/assistant/$f
  done
  # БД и сессия Telegram должны остаться доступны сервисному пользователю
  sudo chown cursor:cursor /opt/assistant /opt/assistant/assistant.db \
       /opt/assistant/tg_user.session
  sudo /opt/assistant/.venv/bin/python -m py_compile /opt/assistant/*.py
  sudo systemctl restart assistant && sleep 8 && curl -s localhost:8800/health
  sudo systemctl restart assistant-telegram
'
```

Тесты: `/opt/assistant/.venv/bin/python -m pytest /opt/assistant/tests -q`
(сети не требуют). Логи: `journalctl -u assistant -f`,
`journalctl -u assistant-telegram -f`.

## Переменные окружения

Секреты лежат только в `/etc/assistant.env` и `/etc/assistant-telegram.env`
(права 600) и в репозиторий не попадают.

Ядро: `OLLAMA_URL`, `OLLAMA_MODEL`, `GATEWAY_URL`, `GATEWAY_KEY`, `GATEWAY_MODEL`,
`LLM_DEFAULT_PROVIDER`, `LLM_PRIVATE_PROVIDER`, `LLM_TIMEOUT`,
`FINANCE_API`, `TG_USER_URL`, `TG_TOKEN`, `TG_ALLOWED_ID`, `ASSISTANT_DB`,
`WHISPER_MODEL`, `EXT_PROXY`, `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_PLACE`,
`TZ_NAME`, `OWNER_NAME`, `OWNER_GENDER`, `ASSISTANT_NAME`, `ASSISTANT_GENDER`,
`RESPONSE_MODE`, `TRUSTED_PEERS`, `ACTION_APPROVAL_TTL`, `ACTION_MAX_ATTEMPTS`,
`ACTION_RETRY_BACKOFF`, `NOTIFY_QUIET_FROM`, `NOTIFY_QUIET_TO`,
`NOTIFY_MIN_INTERVAL`, `MEMORY_MIN_CONFIDENCE`, `MEMORY_INFERENCE_CAP`,
`MEMORY_DEDUPE_THRESHOLD`, `MEMORY_RETRIEVAL_LIMIT`, `EVENT_RETENTION_DAYS`,
`TRADING_CHANNEL`, `NEWS_FEEDS`, `NEWS_CACHE_TTL`, `NEWS_SKIP_CATEGORIES`,
`NEWS_JUNK_EXTRA`, `NEWS_DIRECT_TIMEOUT`, `NEWS_PROXY_TIMEOUT`.

Бот: `TG_TOKEN`, `TG_ALLOWED_ID`, `ASSISTANT_URL`, `TG_USER_URL`, `TG_PROXY`,
`TZ_NAME`, `BRIEFING_TIME`, `EVENING_BRIEFING_TIME` (пусто — вечерний брифинг
только по команде `/evening`), `TG_NEWS_LIMIT`, `TG_NOTIFY_POLL`.

Аккаунт владельца (tg-user): `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`,
`ASSISTANT_URL`, `NOTIFY`, `NOTIFY_GROUPS`, `NOTIFY_COOLDOWN`.

Пример без секретов — `assistant/.env.example`.
