# JARVIS — архитектура

Модульный монолит на Python: один процесс ядра (FastAPI), один процесс
Telegram-бота, один процесс Telegram-аккаунта владельца. Никаких брокеров,
Kafka и Kubernetes — границы модулей держатся кодом, а не инфраструктурой.

## Слои

```
                        ВЛАДЕЛЕЦ
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   Telegram (бот)     голосовое (STT)      HTTP / Web UI
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                    INTERFACE LAYER
              (tg_bot.py, tg_user_service.py, core/api.py)
                            │
                            ▼
                     ┌─────────────┐
                     │ JARVIS CORE │
                     └──────┬──────┘
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
      Context            Agents            Memory
   (core/context)   (agents/personal,    (domain/memory,
                     agents/communication) contacts,
          │                 │              conversations,
          │                 │              episodes,
          │                 │              commitments)
          └────────┬────────┘
                   ▼
            Action Engine (core/actions)
                   │
          Permission Engine (core/permissions)
                   │
                   ▼
             Action Provider (providers/telegram)
                   │
                   ▼
             Внешний сервис (Telegram API)
```

Путь события извне:

```
Integration (tg_user_service)
        │
        ▼
   Event Bus (core/events)
        │
        ├── Agents          — подсказать ответ
        ├── Notifications   — сообщить владельцу
        ├── Memory          — что стоит запомнить
        ├── Audit           — записать в журнал
        └── Enrichment      — саммари, эпизоды, обязательства
```

## Процессы

| Процесс | Файл | Роль |
|---|---|---|
| `assistant` | `assistant.py` + `core/` | Ядро, HTTP API (`:8800`), Web UI (`/ui`), навыки, фоновые воркеры |
| `assistant-telegram` | `tg_bot.py` | Канал владельца: команды, уведомления, кнопки |
| `tg-user` | `tg_user_service.py` | Аккаунт владельца (Telethon): каналы, отправка от его имени. Чужие чаты не собираем |
| `assistant-phone` | `phone/` | Мост с iPhone и Apple Watch (`:8820`): приём по HTTP, выдача по MCP ([phone.md](phone.md)) |

Ядро не хранит логику Telegram, а бот не хранит бизнес-логику: бот забирает
уведомления из очереди ядра и вызывает `/api/*`.

## Модули

```
assistant/
├── core/                 Phase 1 — платформа
│   ├── config.py         типизированная конфигурация из окружения
│   ├── db.py             схема и доступ к SQLite (+ миграции)
│   ├── events.py         Event Bus, каталог типов событий
│   ├── actions.py        Action Engine, ActionProvider, статусы, retry
│   ├── permissions.py    уровни риска, политика, решения
│   ├── notifications.py  Notification Engine, провайдеры, политика доставки
│   ├── llm.py            LLMProvider, реестр, structured output
│   ├── agents.py         базовый Agent, реестр, Pydantic-схемы ответов
│   ├── intents.py        распознавание намерений (правила + опция модели)
│   ├── context.py        Context и ContextResolver
│   ├── audit.py          журнал действий
│   ├── integrations.py   реестр интеграций и health
│   ├── pipeline.py       единый путь сообщения для всех интерфейсов
│   ├── channels.py       чем письмо отличается от сообщения в Telegram
│   ├── mailwatch.py      опрос почтовых ящиков
│   ├── calendarwatch.py  расписание владельца и напоминания о встречах
│   ├── mcp.py            клиент MCP: внешние сервисы и шлюз
│   ├── api.py            Core API (/api/*)
│   ├── security.py       кто имеет право спрашивать ядро
│   └── bootstrap.py      сборка графа объектов
├── web/                  Web UI поверх Core API, без сборки
├── domain/               Phase 2 — предметная область
│   ├── contacts.py       контакты, алиасы, entity resolution, стиль
│   ├── conversations.py  диалоги и сообщения (включая VOICE + транскрипт)
│   ├── memory.py         память: типы, провенанс, дедуп, конфликты, поиск
│   ├── episodes.py       эпизоды
│   ├── commitments.py    обязательства и ожидание ответа
│   └── enrichment.py     фоновая обработка сообщений
├── agents/
│   ├── personal.py       генералист: новости, погода, финансы, брифинги
│   └── communication.py  переписка: подсказки, профиль, обязательства
└── providers/
    ├── telegram.py       единственная точка выхода в Telegram API
    ├── email.py          IMAP и SMTP: чтение и отправка писем
    ├── calendar.py       CalDAV: расписание и запись встреч
    └── mcp.py            вызов инструмента MCP как действие

phone/                    отдельный сервис: мост с iPhone и Apple Watch
├── ingest.py             приём пакетов от ярлыков iOS
├── insights.py           норма человека, отклонения, кто ждёт ответа
├── mcp.py                сервер MCP (2026-07-28 и старые версии)
└── tools.py              инструменты, которые видит модель

backend/app/              финансовое приложение (отдельный сервис в Docker)
├── connectors/           выписки банков: Ozon, CSV/XLSX, PDF, Open Banking
├── mcp/                  сервер MCP: финансы как инструменты для модели
└── services/bank_sync.py импорт операций без повторов
```

Сервисы, которые не влезают в ядро, подключаются как MCP-серверы: ядро знает
только адрес и токен. Шлюз MCP при этом выглядит как ещё один сервер, поэтому
его появление не требует правок.

## Правила слоёв

* `domain/*` не знает про Telegram и HTTP.
* `agents/*` не вызывает внешние API — возвращает текст и заявки на действия.
* Только `providers/*` обращается к внешним сервисам, и только из Action Engine.
* LLM не пишет в БД и не выполняет действий: он отдаёт текст или structured
  output, а ядро решает, что с этим делать.
* Секреты живут в `/etc/assistant.env` и `/etc/assistant-telegram.env`,
  в репозитории — только `.env.example`.
* Чтение из внешнего сервиса по MCP допустимо напрямую (это не поступок);
  всё, что меняет мир, идёт действием `mcp.tool.call`.

## Голос

Голосовые сообщения принимаются и распознаются; ответ всегда текстовый.

```
voice message → getFile → POST /stt → текст → POST /api/chat → текст
```

TTS в проекте нет: модуль синтеза и эндпоинты `/tts`, `/voices` удалены,
`Message.message_type = VOICE` хранит транскрипт для истории.

## Состояние фаз

| Фаза | Состояние |
|---|---|
| Phase 1 — ядро | реализовано и используется Telegram-потоком |
| Phase 2 — память, контакты, диалоги | реализовано |
| Phase 3 — миграция Telegram | реализовано (бот работает через `/api/*`) |
| Phase 4 — Web UI | реализовано ([web.md](web.md)) |
| Phase 5 — почта | реализовано ([email.md](email.md)) |
| Phase 6 — календарь | реализовано ([calendar.md](calendar.md)) |
| Phase 6 — задачи | не начато |
| Phase 7 — телефон и здоровье | реализовано ([phone.md](phone.md)) |
| Phase 8 — банки и Ozon | реализовано ([BANKS.md](BANKS.md), [operations.md](operations.md), [MCP.md](MCP.md)) |
| Phase 9+ — рынки, такси | не начато |
