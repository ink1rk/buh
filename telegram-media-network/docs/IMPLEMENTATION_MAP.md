# Карта реализации

База: код глобального апгрейда на `cursor/tmn-global-upgrade-c7b2`. R9 добавляет продуктовую логику редакции поверх него. Живой опрос, локальная модель, Compose и Telegram по-прежнему выключены.

## Уже было

- Восемь каналов и десять источников в YAML. Bootstrap не создаёт пользователей и не включает публикацию.
- Разбор фикстур, ключи, один основной канал, rubric-v1, детерминированный редактор, карточка `render_card` 1280×720, модерация, outbox, диспетчер.
- `StoryEvidence.verified_at` пустой, статус `extracted`. `auto_approve_allowed()` всегда ложен.
- Админка: вход, обзор, лента, редактор, календарь слотов, источники, публикации, заглушки статистики и рекламы.
- Alembic `0001_initial` … `0003_r7_integrity`. `ENVIRONMENT=production` не стартует.

## Расширено

- `Story`, `Post`, `PublishingOutbox`, `AdCampaign` получили поля кластера, synthetic, снимка подписи и признака DEMO-кампании. Старые колонки не удалялись.
- `SCHEMA_HEAD` стал `0005_r9_product_foundation`. `0001`–`0004` остались. `apply_schema_extras` добавляет новые колонки и на уже созданной тестовой базе.
- `dispatch_outbox` до сети отклоняет synthetic и текст `NEVER_PUBLISH`, а после ответа 200 сверяет версию и хеш подписи со снимком, снятым в момент claim.
- Навигация и страницы обзора, радара, редакции, календаря, студии, программ, аналитики, коммерции и системы. Календарный перенос идёт через сервер с версией; конфликт не двигает строку.
- `render_card` не менялся. Новые композиции живут в `render_network_card`.

## Добавлено

- `app/product/`: учебный пакет, радар 3.0, редакционные паспорта, планировщик 28 дней, рост, коммерция, воронка и DEMO-кампании.
- `app/api/product_routes.py`: чтение и изменения с сессией, CSRF и ролью. Ни один маршрут не создаёт Telegram-транспорт.
- Миграции `0004_global_product` и `0005_r9_product_foundation`: только `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`. Откат `0005` удаляет новые таблицы — это data-destructive.
- Тесты `tests/test_global.py`.
- Скриншоты `reports/screenshots/global/`.

## Не делалось

Не включались `SOURCE_MODE=live`, `LLM_MODE=local`, `TELEGRAM_TRANSPORT=sandbox`, `DRY_RUN=false`, `SPONSORED_ENABLED=true`. Не запускался `docker compose up`. Не менялись Proxmox, файрвол, VPN, NAT, DNS и чужие проекты.
