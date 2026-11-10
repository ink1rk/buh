# R11 Pilot Approval Matrix

Только режим A активирован в этой сборке. Код B–E существует как закрытый контур и не включается переменными окружения.

| Код | Режим | Активирован | Что делает | Что нужно от владельца |
| --- | --- | --- | --- | --- |
| A | `offline_replay` | да | Кассеты, chronological lab, mock/fake LLM | ничего, это текущий контур |
| B | `shadow_live_read` | нет | HTTP-коллекторы по allowlist без публикации | отдельное разрешение, allowlist, журнал |
| C | `local_llm_pilot` | нет | Реальный Ollama `/api/chat` на loopback | URL, модель, таймаут, запись в LLMCallLog |
| D | `telegram_sandbox` | нет | Транспорт sandbox в тестовый чат | бот, chat id, снятие kill switch, dry_run=false |
| E | `production` | нет | Боевая отправка | `ENVIRONMENT=production` по-прежнему отказывается при старте |

`PILOT_MODE` отличный от `offline_replay` останавливает boot. `LLM_MODE=local` без инъекции клиента не открывает сокет. `SOURCE_MODE=live` не активирует коллекторы.

PUBLISH ENABLED? NO.
TELEGRAM SEND COUNT? 0.
LIVE DATA? NO.
REAL REVENUE? UNKNOWN.
PRODUCTION READY? NO.
