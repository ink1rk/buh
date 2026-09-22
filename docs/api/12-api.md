# 12 — API

## 1. Общие принципы

| Принцип | Решение |
|---|---|
| Стиль | REST поверх HTTP/JSON, ресурсы во множественном числе |
| База | `/api/v1` |
| Документация | OpenAPI 3.1 автоматически (`/api/docs`, `/api/openapi.json`) |
| Типы на фронте | Генерация через `openapi-typescript` — контракт не расходится с клиентом |
| Аутентификация | Сессионная cookie (httpOnly) + CSRF-токен на небезопасные методы |
| Ошибки | RFC 7807 `application/problem+json` |
| Конкурентность | `ETag` / `If-Match` на изменяемых ресурсах (`version`) |
| Пагинация | Keyset (`cursor`) для больших коллекций, offset — для отчётных выборок |
| Массовые операции | Отдельные `POST /{resource}/bulk` эндпоинты, транзакционные |
| Идемпотентность | Заголовок `Idempotency-Key` для операций применения изменений |
| Версионирование | Путь `/v1`; ломающие изменения — только в новой версии |

Ответ на ошибку:

```json
{
  "type": "https://itms.local/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "Устройство не помещается в стойку",
  "errors": [
    { "field": "position_u", "code": "rack_overflow",
      "message": "U41 + 2U превышает высоту стойки (42U)" }
  ],
  "request_id": "0f6f…"
}
```

---

## 2. Аутентификация и сессия

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/auth/login` | Вход (логин, пароль) → cookie сессии + CSRF |
| POST | `/auth/logout` | Выход, отзыв сессии |
| GET | `/auth/me` | Текущий пользователь, права, настройки интерфейса |
| POST | `/auth/password` | Смена пароля |
| GET | `/auth/sessions` / DELETE `/auth/sessions/{id}` | Просмотр и отзыв сессий |

Ограничение частоты: 5 неудачных попыток входа за 5 минут на IP+логин.

---

## 3. Универсальные ресурсы CMDB

Базовый объект даёт единый набор операций для всех типов:

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/ci` | Список с фильтрами: `type`, `status`, `criticality`, `location`, `owner`, `tag`, `q`, `updated_after` |
| POST | `/ci` | Создание (тип определяет обязательные поля расширения) |
| GET | `/ci/{id}` | Карточка: базовые поля + расширение типа |
| PATCH | `/ci/{id}` | Частичное изменение (требует `If-Match`) |
| DELETE | `/ci/{id}` | Мягкое удаление |
| POST | `/ci/{id}/restore` | Восстановление |
| GET | `/ci/{id}/related` | **Все связанные объекты, сгруппированные по смыслу** (`?depth=1..3`) |
| GET | `/ci/{id}/graph` | Подграф для визуализации (узлы + рёбра) |
| GET | `/ci/{id}/history` | История изменений (`audit_log` + `audit_change`) |
| GET | `/ci/{id}/provenance?field={name}` | Происхождение значения параметра: кто, когда, почему, в рамках какого проекта/изменения/задачи/документа |
| POST | `/ci/{id}/archive`, `/ci/{id}/restore` | Архивирование вместо удаления |
| GET | `/ci/{id}/documents` / `/tasks` / `/changes` / `/projects` | Связанные сущности |
| POST | `/ci/bulk` | Массовое изменение полей |
| POST | `/ci/import` | Импорт CSV с предпросмотром (`dry_run=true`) |

Типизированные представления — те же объекты с фильтром и расширенной схемой ответа: `/devices`, `/racks`, `/services`, `/applications`, `/vms`, `/clusters`, `/databases`, `/storages`, `/domains`, `/certificates`, `/locations`.

Пример ответа `/ci/{id}/related`:

```json
{
  "ci": { "id": "…", "code": "SRV-1C-01", "ci_type": "DEVICE", "status": "ACTIVE" },
  "groups": {
    "location":   { "path": ["ООО Компания","Площадка Север","Корпус А","2 этаж","Серверная 205"],
                    "rack": { "id": "…", "name": "R1" }, "position_u": 20, "u_height": 2 },
    "runs":       [ { "id": "…", "name": "VM-1C-APP", "ci_type": "VM" } ],
    "depends_on_this": [ { "id": "…", "name": "1С", "ci_type": "SERVICE", "criticality": "CRITICAL" } ],
    "network":    { "interfaces": 4, "connections": [ { "id": "…", "peer": "SW-CORE-01 / Gi1/0/14",
                     "medium": "COPPER", "category": "CAT6A", "status": "ACTIVE" } ] },
    "power":      { "feeds": [ { "side": "A", "path": ["Ввод №1","ЩС-1","QF1","UPS-1","R1-PDU-A","C13-07"] },
                               { "side": "B", "path": ["Ввод №1","ЩС-1","QF2","R1-PDU-B","C13-04"] } ],
                    "estimated_load_w": 840 },
    "people":     { "owner": {…}, "responsible": {…} },
    "documents":  [ { "id": "…", "code": "DOC-0042", "title": "Паспорт сервера" } ],
    "projects":   [ { "id": "…", "key": "PWR", "name": "Увеличение мощности серверной" } ],
    "tasks":      { "open": 2, "overdue": 0, "items": [ … ] },
    "changes":    [ { "code": "CHG-0031", "status": "SCHEDULED" } ]
  }
}
```

Это ключевой эндпоинт системы: он реализует требование «любой объект показывает связанные объекты».

---

## 4. Связи

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/relations` | Список рёбер с фильтрами (`source`, `target`, `type`) |
| POST | `/relations` | Создать связь (проверка цикла для `DEPENDS_ON`) |
| PATCH/DELETE | `/relations/{id}` | Изменить/удалить |
| GET | `/graph` | Подграф по фильтру (площадка, сервис, проект, глубина) |
| GET | `/impact/{ci_id}` | Анализ влияния: сервисы, простой, резерв, объяснение |

---

## 5. Сеть

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/devices/{id}/interfaces` | Порты устройства, создание (в т.ч. из шаблона модели) |
| PATCH/DELETE | `/interfaces/{id}` | Изменение порта |
| GET | `/interfaces/free` | Свободные порты с фильтрами по типу/устройству/площадке |
| GET/POST | `/connections` | Кабели: список, создание (валидация портов) |
| PATCH/DELETE | `/connections/{id}` | Изменение, удаление |
| GET | `/connections/{id}/trace` | Сквозная трассировка линка через патч-панели |
| GET/POST | `/vlans`, `/prefixes`, `/ip-addresses`, `/vrfs` | Адресация |
| GET | `/prefixes/{id}/utilisation` | Занятость подсети, свободные адреса |
| GET | `/ip-addresses/lookup?address=10.20.5.17` | Кому принадлежит адрес |

---

## 6. Стойки и план

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/racks` | Список со сводкой занятости (U, вес, мощность) |
| GET | `/racks/{id}/elevation` | Полный состав стойки по фасадам для редактора |
| POST | `/racks/{id}/mounts` | Разместить оборудование (валидация U, фасада, веса) |
| PATCH | `/mounts/{id}` | Переместить / изменить фасад |
| DELETE | `/mounts/{id}` | Извлечь (объект → `IN_STOCK`) |
| POST | `/racks/{id}/validate-placement` | Предпроверка без записи (для drag & drop) |
| GET | `/racks/{id}/free-space` | Непрерывные свободные блоки U |
| GET/POST | `/floorplans`, `/floorplans/{id}/items` | Планы помещений |

`validate-placement` вызывается во время перетаскивания (дебаунс) и возвращает `{ "ok": false, "reason": "overlap", "conflicts": [...] }` — это позволяет подсвечивать зону до отпускания мыши.

---

## 7. Питание

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/power/nodes` | Узлы электрической модели |
| GET/POST | `/power/links` | Связи питания (проверка ацикличности) |
| GET | `/power/tree?root={id}` | Дерево питания от узла вниз |
| GET | `/power/nodes/{id}/load` | Нагрузка, резерв, токи, **трасса расчёта** |
| POST | `/power/recalculate` | Принудительный пересчёт области |
| GET | `/power/summary?location={id}` | Сводка по помещению: ввод, нагрузка, резерв, фазы |
| GET/POST | `/power/feeds` | Ветки питания (лучи A/B): состав, защита, корневой ввод |
| GET | `/power/feeds/{id}/failover-analysis` | «Что перестанет работать при отказе этой ветки» с вердиктом по каждому потребителю |
| GET/POST | `/power/nodes/{id}/measurements` | История фактических измерений: значение, дата, источник, прибор |
| GET | `/power/phase-balance?location={id}` | Баланс фаз, дисбаланс, рекомендации по переносу нагрузки |
| GET/POST | `/power/scenarios` | Сценарии «что если» |
| POST | `/power/scenarios/{id}/calculate` | Расчёт сценария: до / после / дефицит |
| POST | `/power/scenarios/{id}/to-planned-change` | Превратить сценарий в целевое состояние проекта |

---

## 8. Диаграммы

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/diagrams` | Список, создание (в т.ч. с автонаполнением по `scope`) |
| GET | `/diagrams/{id}/full` | Узлы + рёбра + актуальные данные объектов одним запросом |
| PATCH | `/diagrams/{id}/layout` | Сохранение раскладки (только изменённые узлы) |
| POST | `/diagrams/{id}/nodes` / DELETE `/diagram-nodes/{id}` | Добавить/убрать объект со схемы |
| POST | `/diagrams/{id}/autolayout` | Серверная автораскладка (опционально) |
| POST | `/diagrams/{id}/export` | SVG / PNG / PDF / JSON → файл в MinIO |
| GET | `/diagrams/{id}/diff?planned_change={id}` | Режим сравнения CURRENT / TARGET |

---

## 9. Проекты и задачи

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/projects` | Список, создание (в т.ч. из шаблона) |
| GET | `/projects/{id}` | Паспорт + агрегаты + здоровье |
| GET | `/projects/{id}/gantt` | Данные Gantt: задачи, зависимости, критический путь, baseline |
| GET/POST | `/projects/{id}/phases`, `/milestones`, `/risks`, `/budget-items` | Состав проекта |
| GET/POST | `/projects/{id}/snapshots` | Снимки CURRENT STATE |
| GET/POST | `/projects/{id}/planned-changes` | Целевое состояние |
| GET | `/planned-changes/{id}/gap-analysis` | Дефициты: мощность, место, порты, адреса |
| POST | `/planned-changes/{id}/apply` | Применить к модели (транзакционно, идемпотентно) |
| GET | `/planned-changes/{id}/rollback-plan` | Сгенерированный план отката |
| GET/POST | `/tasks` | Задачи всех типов с фильтрами |
| PATCH | `/tasks/{id}` | Изменение (inline-правки из списка/доски) |
| POST | `/tasks/bulk` | Массовые операции |
| POST | `/tasks/{id}/move` | Перемещение в Kanban (статус + порядок) |
| GET/POST | `/tasks/{id}/dependencies` | Зависимости |
| GET/POST | `/tasks/{id}/time-entries` | Учёт времени |
| GET | `/workload?week=2026-09-21` | Загрузка сотрудников по дням |

---

## 10. Эксплуатация

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/changes` | Изменения |
| POST | `/changes/{id}/transition` | Переход статуса с проверкой обязательных полей |
| GET/POST | `/changes/{id}/approvals` | Согласования, включая внешние стороны |
| GET | `/changes/{id}/impact` | Анализ влияния |
| GET/POST | `/incidents`, `/problems` | Инциденты и проблемы |
| GET/POST | `/maintenance-windows` | Окна работ (проверка пересечений) |
| GET | `/calendar?from=&to=` | Единый календарь: работы, окна, вехи, сроки |

---

## 11. Документы и файлы

| Метод | Путь | Назначение |
|---|---|---|
| GET/POST | `/documents` | Документы с фильтрами (тип, статус, пересмотр, связи) |
| GET | `/documents/{id}` | Документ + текущая версия |
| POST | `/documents/{id}/versions` | Новая версия |
| GET | `/documents/{id}/versions/{n}/diff?to=m` | Сравнение версий |
| POST | `/documents/{id}/transition` | Смена статуса (утверждение) |
| GET/POST | `/documents/{id}/links` | Связи с объектами |
| POST | `/files` | Загрузка (проверка MIME, санация имени) |
| GET | `/files/{id}/download` | Подписанная ссылка / поток |
| GET | `/folders` | Дерево папок |

---

## 12. Поиск

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/search?q=…&types=ci,document,task&limit=20` | Глобальный поиск |
| GET | `/search/suggest?q=…` | Подсказки для командной палитры (быстрый префиксный поиск) |

Ответ содержит тип, заголовок, подзаголовок, путь размещения, подсветку совпадения и **краткий список связей** (стойка, сервис, проект) — чтобы результат был полезен без перехода.

---

## 13. Отчёты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/reports/datasets` | Каталог датасетов с полями и допустимыми фильтрами |
| GET/POST | `/reports` | Сохранённые определения отчётов |
| POST | `/reports/{id}/run` | Запуск (синхронно или как `job`) |
| POST | `/reports/preview` | Предпросмотр без сохранения определения |
| GET | `/reports/runs/{id}` | Статус и ссылка на файл |

---

## 14. Служебное

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/dashboard` | Данные дашборда одним запросом (по включённым блокам) |
| GET | `/notifications`, POST `/notifications/read` | Уведомления |
| GET | `/audit` | Журнал аудита с фильтрами |
| GET | `/jobs/{id}` | Статус фоновой задачи |
| GET | `/health`, `/ready`, `/metrics` | Эксплуатация самой системы |
| GET | `/export/backup` | Полный JSON-экспорт модели (для переноса/архива) |

---

## 14a. Заголовки происхождения изменения

Любой изменяющий запрос может нести контекст происхождения. Заголовки попадают в `contextvars` и автоматически проставляются во все записи `audit_log`, созданные в рамках запроса:

```
X-Change-Id:  550e8400-…     изменение, в рамках которого выполняется правка
X-Project-Id: 7c9e6679-…     проект
X-Task-Id:    3fa85f64-…     задача
X-Reason:     замена БП на 850 Вт
```

Интерфейс подставляет их автоматически, когда пользователь открыл объект из задачи, изменения или проекта. Для критичных полей (статус, размещение, электрические параметры, владелец, вывод из эксплуатации) отсутствие и ссылки, и причины приводит к ответу `422 provenance_required`.

---

## 15. Соглашения по фильтрации и сортировке

```
GET /tasks?status=IN_PROGRESS,REVIEW
          &assignee=e3f1…
          &due_before=2026-10-01
          &project=PWR
          &ci=8f22…
          &q=коммутатор
          &sort=-priority,due_date
          &cursor=eyJpZCI6…
          &limit=50
```

- Перечисления через запятую = условие `IN`.
- Префикс `-` в `sort` = убывание.
- `q` — полнотекстовый поиск по датасету.
- Ответ коллекции: `{ "items": [...], "next_cursor": "…", "total": 1234 }` (`total` — по запросу `with_total=true`, чтобы не считать зря).

## 16. Права

В текущем режиме проверки сводятся к «владелец системы имеет полный доступ», но реализованы через общий механизм: у каждого эндпоинта объявлено требуемое разрешение (`ci:write`, `power:calculate`, `report:export`). Включение ролей исполнителей позже не потребует переписывания обработчиков.
