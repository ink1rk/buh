# R10 — Telegram Media Network 3.0, 10 ноября 2026

Время прогона: 23:21 Europe/Moscow. База R9: ветка `cursor/tmn-r9-product-c7b2`, коммит `ab28d0e` (код `365cd93`). Эта поставка: ветка `cursor/tmn-r10-mega-c7b2`. Это офлайн-редакционная платформа восьми каналов с 30-дневной лабораторией. Production не заявлялся. Live-проверка не заявлялась.

Флаги поставки не менялись: `DRY_RUN=true`, `PUBLISH_ENABLED=false`, `GLOBAL_KILL_SWITCH=true`, `SPONSORED_ENABLED=false`, `SOURCE_MODE=offline`, `LLM_MODE=mock`. `ENVIRONMENT=production` по-прежнему не стартует. Транспорт Telegram при этих флагах — `None`.

Как вернуться к baseline: `git checkout cursor/tmn-r9-product-c7b2`. Не делать `alembic downgrade 0006` — откат запрещён кодом, это потеря редакционной истории. Forward-fix.

## Итоговая формула

- `R10 OFFLINE PRODUCT: PASS`
- `SOURCE INGEST LIVE: NOT RUN (NOT AUTHORIZED)`
- `LLM LOCAL LIVE: NOT RUN (NOT AUTHORIZED)`
- `TELEGRAM SEND: 0`
- `REAL AUDIENCE / REVENUE: UNKNOWN`
- `PRODUCTION READY: NO`
- `T17–T20: BLOCKED`

## Статусы P0–P11

| Блок | Статус | Метка |
| --- | --- | --- |
| P0 дефекты R9 | календарь 7/28, тренд, издатели, overflow, forecast label, data_mode, claims, evergreen | UNIT TESTED и браузер |
| P1 Signal Intelligence 4.0 | rank-v4, snapshot, CVE/release identity, reprints | UNIT TESTED |
| P2 Research Desk | досье, claims ledger, независимый publisher | UNIT TESTED и браузер |
| P3 Editorial Factory | brief/variants, паспорт, mock LLM contract | UNIT TESTED и браузер |
| P4 Visual Studio 3.0 | 48 JPEG 16:9, ratios 1:1 и 4:5 одним engine | UNIT TESTED и страница |
| P5 Smart Calendar 3.0 | 7 vs 28 колонок, пустоты, 409 конфликта | UNIT TESTED и браузер |
| P6 Workflow Engine | 12 стадий, idempotency, pause/resume, delivery_allowed=false | UNIT TESTED и браузер |
| P7 Growth | lineage, null vs 0 vs DEMO, views unknown | UNIT TESTED и браузер |
| P8 Commercial OS 2.0 | offer → reserve → cancel, цены proposal/null | UNIT TESTED и браузер |
| P9 Mission Control | досье, паспорт, автопилот, лаборатория, смена | UNIT TESTED и браузер |
| P10 30-day lab | идемпотентный прогон, 8 каналов, Telegram 0 | UNIT TESTED и браузер |
| P11 schema 0006 | additive, 0001→head и 0005→head | UNIT TESTED |
| T17–T20 | как в R9 | BLOCKED |

## Приёмка A01–A22

| ID | Результат | Доказательство |
| --- | --- | --- |
| A01 | PASS | R8/R9 тесты зелёные, SCHEMA_HEAD `0006_r10_media_os` |
| A02 | PASS | DEMO/synthetic не публикуется, транспорт `None` |
| A03 | PASS | CVE-2026-880001 ≠ 880099, v1.0 ≠ v2.0 |
| A04 | PASS | два снимка stars 100→140, один — unknown |
| A05 | PASS | rss_mirror не добавляет независимого издателя |
| A06 | PASS | claims не `independently_verified` по URL |
| A07 | PASS | общий инфоповод, ≥3 разных variant body |
| A08 | PASS | радар → досье → редакция без ввода ID поста |
| A09 | PASS | длинный заголовок → `fits=False`, `headline_overflow` |
| A10 | PASS | 48 уникальных JPEG, ratios 1280×720 / 1080×1080 / 1080×1350 |
| A11 | PASS | CSS-классы `days-7`/`days-28`, computed 8 vs 29 колонок |
| A12 | PASS | breaking не растягивается, пустоты `нет материала` |
| A13 | PASS | workflow idempotency; календарь 409 `version_conflict` |
| A14 | PASS | pause/resume, `delivery_allowed` всегда false |
| A15 | PASS | ingested db_derived, views н/д |
| A16 | PASS | actual_label следует за amount |
| A17 | PASS | offer/reserve/cancel в API и форме, published 0 |
| A18 | PASS | VIEWER/EDITOR не грузят lab, CSRF обязателен |
| A19 | PASS | 60 PNG после реальных переходов, 375/768/1280/1600 |
| A20 | PASS | lab run 1, повтор идемпотентен, 8 каналов |
| A21 | PASS | Telegram send 0, флаги R9 не ослаблены |
| A22 | PASS | ZIP + отчёты + шара в новом каталоге |

Объединение на радаре всё ещё просит два числовых id. Это не ломает сквозной маршрут; в ограничениях.

## Что видно оператору

1. Обзор сети, паспорта, «н/д» аудитории, вход в лабораторию и утреннюю смену.
2. Радар: score, 3 причины, data_mode, тренд, Досье / В редакцию / Отклонить без ввода ID карточки.
3. Досье CVE-2026-880001: хронология origin→reprint→update→vendor, один независимый издатель `cisa`.
4. Редакция: факты, варианты, QA `synthetic_never_publish`, превью подписи, кнопка отправки не вызывает Telegram.
5. Студия: шесть назначений на бренд, 48 JPEG.
6. Календарь 7/28: разное число колонок, пустые слоты с причиной, proposed ≠ scheduled, 409 при чужой версии.
7. Автопилот: стадии, пауза/продолжить, «доставка заблокирована политикой».
8. Рост: ingested 38, published 0, просмотры н/д.
9. Коммерция: воронка лидов, предложение/резерв/отмена, факт выручки н/д.
10. Лаборатория: 30 сюжетов, 38 исходных записей, Telegram send = 0.

Walkthrough: войти как owner, «Загрузить 30-дневную лабораторию», Обзор → Радар CVE → Досье → Редакция → Студия → Календарь 28 → конфликт слота → Рост → Коммерция → экспорт. Сервер после проверки остановлен.

## Команды

Из `telegram-media-network`, около 23:21 Europe/Moscow:

```text
.venv/bin/python -m compileall -q app alembic tests scripts
.venv/bin/pytest -q --tb=line
.venv/bin/ruff check app tests
.venv/bin/mypy app
DATABASE_URL=.../tmn_r10_mig .venv/bin/alembic upgrade head
DATABASE_URL=.../tmn_r10_from5 .venv/bin/alembic upgrade 0005_r9_product_foundation
DATABASE_URL=.../tmn_r10_from5 .venv/bin/alembic upgrade head
.venv/bin/python scripts/r10_browse.py
```

Pytest: 180 passed, пропусков и xfail нет. Ruff чистый. Mypy: 79 файлов без ошибок. Alembic `0001→head` и `0005→head` дают `0006_r10_media_os`. Браузер: headless Chrome, 60 скриншотов `reports/screenshots/r10/`, 48 карточек `reports/screenshots/r10/cards/`, три пропорции `reports/screenshots/r10/ratios/`. Конфликт слота: `409 version_conflict`. Повтор `load_lab`: `idempotent true`.

## Явные ответы

- PUBLISH ENABLED? NO
- TELEGRAM SEND COUNT? 0
- LIVE DATA? NO
- REAL REVENUE? UNKNOWN
- PRODUCTION READY? NO

## KNOWN_LIMITATIONS

- Нет разрешения на живые API, локальную модель, тестовый бот и тестовый канал.
- Нет разрешения менять файрвол или поднимать Compose. T17–T20 остаются BLOCKED.
- Монетизация и аудитория остаются «н/д».
- Форма «Объединить» на радаре всё ещё принимает два числовых id.
- Строка формулы воронки на экране «Рост» остаётся технической (английские идентификаторы стадий).
- KPI «запланированы» на обзоре считает outbox, а не proposed-слоты календаря: это ноль отправок, не пустой месяц.
- Пакет 48 карточек — 16:9; 1:1 и 4:5 проверяются тем же engine на отдельных файлах.
- Адаптер `LLM_MODE=local` всегда `local_provider_disabled` в этом релизе.
