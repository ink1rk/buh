# Мост с телефоном (`jarvis-phone`)

Отдельный сервис: забирает здоровье, звонки и переписку из первоисточников
Apple и отдаёт их наружу как MCP-сервер. Живёт своим процессом на `:8820`
и своей базой `phone.db`.

```
export.zip / Health Auto Export / chat.db / CallHistory
        ──▶  phone.db  ──▶  /mcp  ──MCP──▶ Джарвис, Cursor, шлюз
```

| Файл | Что делает |
| --- | --- |
| `config.py` | настройки из окружения |
| `store.py` | SQLite: устройства, события, курсоры источников, очередь |
| `ingest.py` | терпимый разбор форматов Apple и Health Auto Export |
| `metrics.py` | справочник метрик Здоровья: любое имя Apple → один ключ |
| `insights.py` | норма человека, отклонения, кто ждёт ответа |
| `apple/` | выгрузка Здоровья, chat.db, CallHistory, копия iPhone, агент |
| `mcp.py` | протокол MCP |
| `tools.py` | инструменты, которые видит модель |
| `server.py` | HTTP: `/v1/*` для пакетов, `/mcp` для моделей |

## Запуск

```bash
python -m phone                            # HTTP на 127.0.0.1:8820
python -m phone --stdio                    # MCP по stdio
python -m phone import-health export.zip   # вся история Здоровья
python -m phone mac-sync --watch           # звонки и iMessage с Mac
python -m phone import-backup              # то же из копии iPhone
python -m pytest phone/tests -q
```

Как настроить источники, приватность, деплой и подключение к ядру —
в [docs/phone.md](../docs/phone.md).
