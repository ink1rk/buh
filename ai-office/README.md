# AI Office

Личный контур: Telegram gateway, оркестратор задач, tool broker и временные Jobs. Код живёт здесь. Кластер — отдельная VM, не хост Proxmox.

## Стек

Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL. Контейнер gateway запускается от непривилегированного пользователя и слушает только localhost внутри образа; наружу его выводит уже сеть кластера.

## Проверки

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
```

## Конфигурация

Секреты только в `.env` или Secret кластера. Образец без значений: `.env.example`.

Состояние задачи: `created → queued → running → waiting_approval / waiting_external → succeeded / failed / cancelled`. Повтор Telegram update и повторный ключ идемпотентности не создают второе внешнее действие.

## Кластер

Манифесты: `deploy/k3s/`. Часовой пояс, токен бота и ключи моделей в репозиторий не входят. Что уже сделано и что дальше: `STATUS.md`. Ограничения: `BLOCKERS.md`. Протокол проверок: `TEST_RESULTS.md`.
