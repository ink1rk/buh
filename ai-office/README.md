# AI Office

Личный контур: Telegram gateway, оркестратор задач, tool broker и временные Jobs. Код живёт здесь. Кластер — отдельная VM, не хост Proxmox.

## Стек

Рабочий контур на VM — пакет `aioffice`: FastAPI, SQLAlchemy, PostgreSQL, Telegram polling, Cursor/Grok через отдельный bridge, launcher заданий и пустой LiteLLM без ключей провайдеров. Ранний каркас в `apps/` и `packages/` остаётся для прежних 15 pytest. Секреты, LAN-адреса и список владельцев в git не входят. Что уже проверено на VM: `STATUS.md`.

## Проверки

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
python3 -m unittest tests.test_policy tests.test_features
```

## Конфигурация

Секреты только в `.env` или Secret кластера. Образец без значений: `.env.example`.

Состояние задачи: `created → queued → running → waiting_approval / waiting_external → succeeded / failed / cancelled`. Повтор Telegram update и повторный ключ идемпотентности не создают второе внешнее действие.

## Кластер

Манифесты раннего каркаса: `deploy/k3s/`. Что работает на VM и что дальше: `STATUS.md`. Ограничения: `BLOCKERS.md`. Протокол проверок рабочей реализации: `TEST_RESULTS.md`. Секреты в репозиторий не входят.
