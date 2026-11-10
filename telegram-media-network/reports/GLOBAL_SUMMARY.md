# Сводка глобального обновления, 10 ноября 2026

Время прогона: около 19:30 Europe/Moscow. База: R8 `ce24618215cc00655606ad7a17560fe10c194208` и отчёт `be66eae13bf3d06957897b0a158f2787e5389534`. Код этой поставки: `e5efe19878073e7b22ca010259e9c2cd2b126013`. Это офлайн-редакция восьми каналов. Production не заявлялся. Live-проверка не заявлялась.

Флаги поставки не менялись: `DRY_RUN=true`, `PUBLISH_ENABLED=false`, `GLOBAL_KILL_SWITCH=true`, `SPONSORED_ENABLED=false`, `SOURCE_MODE=offline`, `LLM_MODE=mock`. `ENVIRONMENT=production` по-прежнему не стартует. Транспорт Telegram при этих флагах — `None`.

Каналы: ai_news, ai_tools, github, cyber, infra, homelab, dev, future. Источников 10. У cyber два подтверждающих. Учебный пакет даёт 24 черновика, по три на канал, все synthetic и `NEEDS_REVIEW`.

## Статусы

| Блок | Статус | Метка |
| --- | --- | --- |
| G1 Радар | сделано офлайн | UNIT TESTED |
| G2 Черновики | сделано офлайн | UNIT TESTED |
| G3 Студия, 32 JPEG | сделано офлайн | UNIT TESTED и страница в браузере |
| G4 Пульт | сделано локально | UNIT TESTED и браузер 375/1280 |
| G5 Программы | сделано офлайн, только `proposed` | UNIT TESTED |
| G6 Воронка | измеренные нули публикаций, просмотры «н/д» | UNIT TESTED |
| G6 Кампании | две DEMO, факт `NULL` | UNIT TESTED |
| SEC-01 транспорт | `None` | STATIC VERIFIED |
| SEC-02 synthetic / NEVER_PUBLISH | диспетчер режет до сети | UNIT TESTED, отправка выключена |
| SEC-03 гонка текста | mock 200 не становится published | UNIT TESTED, живой send BLOCKED |
| OPS-01 Alembic 0004 | строка, вставленная на 0003, сохраняется | UNIT TESTED |
| OPS-02 Compose | не запускался | BLOCKED |
| T17–T20 | как в R8 | BLOCKED |
| T19 живые API и локальная LLM | не включались | BLOCKED |
| T20 Telegram sandbox | не включался | BLOCKED |

## Команды

Из `telegram-media-network`, около 19:25 Europe/Moscow:

```text
.venv/bin/pytest -q --tb=line
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/python -m compileall -q app alembic tests
```

Pytest: 147 passed, пропусков и xfail нет. Ruff чистый. Mypy: 70 файлов без ошибок. Браузер: headless Chrome на `127.0.0.1:8787`, владелец, кнопка учебного пакета, радар, редактор, студия, календарь. Устаревшая версия переноса получила 409. Сервер после проверки остановлен.

## Миграция

`0004_global_product` аддитивная. Откат удаляет новые таблицы и три новые колонки. Это не безопасный откат, если строки уже нужны. Подробности в `docs/DEFERRED_RELEASE_BLOCKERS.md`. Карта: `docs/IMPLEMENTATION_MAP.md`.

## Остаток

Нет разрешения на живые API, локальную модель, тестовый бот и тестовый канал. Нет разрешения менять файрвол или поднимать Compose. Монетизация остаётся «н/д».
