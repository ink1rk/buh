# R10 offline lab

Прогон `1` (title `offline-30d`), старт `2026-10-12 09:00 Europe/Moscow`. Повторная загрузка идемпотентна: `true`. Telegram send: 0. PublishedMessage: 0.

Создано исходных записей: 38. Снимков: 38. Сюжетов: 30. Связей: 2. TrendSample: 2. Workflow: 12. Предложений: 2 (лабораторный путь lead→offer→reserve→cancel плюс форма UI).

## Каналы

| Канал | Сюжеты | Посты | Слоты |
| --- | --- | --- | --- |
| ai_news | 4 | 3 | 0 |
| ai_tools | 3 | 3 | 2 |
| github | 4 | 3 | 1 |
| cyber | 4 | 3 | 1 |
| infra | 2 | 2 | 0 |
| homelab | 5 | 3 | 0 |
| dev | 4 | 3 | 3 |
| future | 4 | 3 | 0 |

Пустые слоты на 28 дней оставлены честно (`skipped`: 297), breaking не растягивался. Evergreen NAS-гайд живёт отдельным ключом от релиза.

Сценарии в потоке: CVE-2026-880001 (бюллетень → RSS → уточнение версий → патч), CVE-2026-880099 отдельно, acme/lab-runner v1.0 и v2.0, лицензия MIT как обновление v1.0, stars 100→140, инструмент HF, препринт+комментарий, injection, общий инфоповод двух редакций.

Пошаговые срезы `tick_day` 1/15/30: clusters=30, posts=23, episodes=7, telegram_send=0.

Машинный отчёт: `reports/lab-results.json`.

PRODUCTION READY: NO
