# Интеграции

`core/integrations.py`. Каждая внешняя система регистрируется в реестре и
умеет отвечать на один вопрос: жива ли она. Ядро не знает, как устроен API
конкретного сервиса.

## Интерфейс

```python
class Integration:
    name = "telegram.bot"
    type = "messaging"
    required = True
    def configured(self): ...
    def health_check(self): ...   # -> (Status, detail)
    def connect(self): ...
    def disconnect(self): ...
```

Статусы: `CONNECTED`, `DEGRADED`, `ERROR`, `NOT_CONFIGURED`, `DISABLED`.

Смена статуса публикует `integration.status.changed`, текущее состояние
хранится в таблице `integrations`, так что агенты могут узнать, что
возможность сейчас недоступна, не дёргая сеть.

## Зарегистрированы сейчас

| Интеграция | Тип | Проверка | Обязательна |
|---|---|---|---|
| `database` | storage | запрос к SQLite + счётчики таблиц | да |
| `email` | email | вход в каждый ящик по IMAP | нет |
| `llm.local` | llm | `GET /api/tags` у Ollama | да |
| `llm.gateway` | llm | `GET /v1/models` у шлюза | да |
| `telegram.bot` | messaging | `getMe` через прокси | да |
| `telegram.user` | messaging | `/health` сервиса tg-user + признак авторизации | нет |
| `finance` | finance | `GET /networth` у финансового API | нет |
| `mcp.<имя>` | mcp | перечисление инструментов на сервере MCP | нет |

Серверы MCP берутся из `MCP_SERVERS`, по одной интеграции на каждый: мост с
телефоном (`mcp.phone`), а дальше всё, что подключится к шлюзу. Проверка —
`tools/list`, а не `ping`: сервер может отвечать на пинг и при этом не иметь
доступа к собственным данным.

## Проверки

* при запуске и далее раз в 5 минут — фоновый воркер ядра;
* по запросу — `GET /api/integrations?refresh=true`;
* сводно — `GET /api/health` (статус `degraded`, если упало обязательное).

В Telegram то же самое доступно командой `/status`:

```
🩺 Интеграции
🟢 database — actions: 3, memories: 2, contacts: 2
🟢 llm.local — qwen2.5:7b-instruct
🟢 llm.gateway — cursor-grok-4.6-high-fast
🟢 telegram.bot — ok
🟢 telegram.user — авторизован
🟢 finance — ok
```

## Точки расширения

Интеграция, у которой ещё нет провайдера действий, добавляется как класс с
`health_check()`; действия к ней подключаются отдельно через `ActionProvider`
(см. `docs/actions.md`). Планируемые: `calendar`, `bank`, `market`, `ozon`,
`taxi`.

Сервис, который тянет на отдельный процесс (свой формат данных, свой поток
входящих, своя база), подключается не классом, а по MCP: `MCP_SERVERS` и
токен. Так сделан мост с телефоном — `docs/phone.md`.

Заглушек, имитирующих работу несуществующего сервиса, в проекте нет: если
интеграции нет, она не зарегистрирована, а действие завершается честной
ошибкой «нет провайдера».

## Секреты

Конфигурация — только через окружение (`core/config.py`). Файлы с секретами
живут на сервере: `/etc/assistant.env`, `/etc/assistant-telegram.env`; в
репозитории — `.env.example`. В журнал аудита значения полей с именами вида
`token`, `password`, `secret`, `api_key` не попадают: они маскируются.
