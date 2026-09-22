# ITMS — архитектурная документация

Пакет документов описывает **IT Management System** — self-hosted систему управления ИТ-инфраструктурой, ИТ-отделом, проектами, эксплуатацией и документацией.

> **Статус:** архитектурное проектирование завершено, ожидает согласования.
> Реализация начинается после утверждения модели (см. `roadmap/14-roadmap.md`, Phase 0 → Phase 1).

## Порядок чтения

| № | Документ | О чём |
|---|---|---|
| 01 | [architecture/01-system-architecture.md](architecture/01-system-architecture.md) | Границы системы, слои, модули, сквозные механизмы, стек, ключевые решения |
| 02 | [domain-model/02-domain-model.md](domain-model/02-domain-model.md) | Configuration Item, связи, статусные модели, аудит, произвольные поля, инварианты |
| 03 | [domain-model/03-entity-map.md](domain-model/03-entity-map.md) | Полный список сущностей, карта связей, матрица «что с чем связано», объёмы данных |
| 04 | [database/04-database-model.md](database/04-database-model.md) | Схема PostgreSQL: таблицы, ключи, индексы, ограничения, миграции |
| 05 | [domain-model/05-infrastructure-model.md](domain-model/05-infrastructure-model.md) | Физика, сеть, интерфейсы, кабели, трассировка, адресация, влияние |
| 06 | [architecture/06-diagram-engine.md](architecture/06-diagram-engine.md) | Редактор схем: модель, взаимодействие, автораскладка, экспорт, режим CURRENT/TARGET |
| 07 | [architecture/07-rack-and-power.md](architecture/07-rack-and-power.md) | Редактор стоек и электрическая модель: правила размещения, методика расчёта, сценарии |
| 08 | [domain-model/08-project-management.md](domain-model/08-project-management.md) | Проекты, Gantt, план/факт, CURRENT STATE → TARGET STATE, сквозной сценарий |
| 09 | [domain-model/09-documentation.md](domain-model/09-documentation.md) | База знаний: типы, версии, пересмотры, связи, шаблоны |
| 10 | [domain-model/10-it-operations.md](domain-model/10-it-operations.md) | Change Management, инциденты, проблемы, плановые работы, управление отделом, дашборд |
| 11 | [architecture/11-reporting.md](architecture/11-reporting.md) | Датасеты, конструктор отчётов, аналитика, экспорт PDF/XLSX/CSV |
| 12 | [api/12-api.md](api/12-api.md) | Контракт REST API, соглашения, ключевые эндпоинты |
| 13 | [ui/13-ui-architecture.md](ui/13-ui-architecture.md) | Каркас интерфейса, структура фронтенда, состояние, паттерны, горячие клавиши |
| 14 | [roadmap/14-roadmap.md](roadmap/14-roadmap.md) | Фазы реализации, критерии выхода, риски, вопросы к согласованию |

## Ключевая идея в одном абзаце

В системе нет независимых разделов. Есть единый граф объектов ИТ-ландшафта (`ci` + типизированные расширения + связи) и его проекции: таблицы, карточки, схемы сети, стойки, электрическая модель, планы помещений, проекты, отчёты. Любой объект показывает все связанные с ним объекты и полную историю изменений. Проект описывает не список задач, а переход инфраструктуры из текущего состояния в целевое — и по завершении обновляет модель.

## Стек

**Backend:** Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · Alembic · PostgreSQL 16 · Redis · ARQ · MinIO
**Frontend:** React 19 · TypeScript · Vite · Tailwind CSS v4 · Radix UI · TanStack Query/Table · Zustand · React Flow · собственные SVG-редакторы (стойки, планы, Gantt)
**Инфраструктура:** Docker Compose. Без Kubernetes, Elasticsearch, внешних SaaS и CDN — система работает в закрытом контуре.

## Что сознательно не делается

AI, Telegram, мобильное приложение, публичная регистрация, multi-tenant, микросервисы, Kubernetes, Elasticsearch, HelpDesk-портал для конечных пользователей. Интеграции (SNMP, Zabbix, AD/LDAP, Veeam, Git) не реализуются сейчас, но архитектура содержит Integration Layer, чтобы добавить их без переписывания ядра.
