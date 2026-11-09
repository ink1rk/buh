# Этап 1. Каркас

Время проверки: 10 ноября 2026, 02:30 по Москве (UTC+3). Статус: PASS по локальным проверкам конфигурации и ролей.

Команда: `.venv/bin/pytest -q` в `telegram-media-network`. 57 тестов, 0 ошибок. Сюда входят A02–A06 и E01–E03.

## Что есть

- `app/core/config.py` читает YAML каналов и не принимает `ENVIRONMENT=production`.
- `app/core/models.py` и миграция `alembic/versions/0001_initial.py` создают схему. Частичный индекс не даёт двум активным записям outbox висеть на одном посте.
- Роли OWNER, EDITOR, REVIEWER_SECURITY, VIEWER, SERVICE. Пароль Argon2id, сессия в хэше cookie, CSRF в заголовке. Сам себя повысить нельзя. Пять ошибок входа за 15 минут дают 429.
- `configs/channels.yaml`: восемь каналов, `publish_enabled: false`, quiet hours 22:00–08:00, `daily_cap: 2`, пауза 240 минут, реклама выключена, kill switch включён.

## Доказательства

- `tests/test_a_config.py`
- `tests/test_e_security.py` для входа, MFA и запрета эскалации
