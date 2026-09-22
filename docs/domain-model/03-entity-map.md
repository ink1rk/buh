# 03 — Карта сущностей и связей

Полный перечень сущностей системы с указанием модуля, назначения и ключевых связей. Это оглавление модели данных; физическая схема — в `docs/database/04-database-model.md`.

## 1. Сводная карта модулей

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ DIRECTORY        organization · department · employee · app_user · role      │
└───────────┬─────────────────────────────────────────────────────────────────┘
            │ owner / responsible / assignee
┌───────────▼─────────────────────────────────────────────────────────────────┐
│ CMDB (ядро)      ci · ci_relation · location · device · device_model ·       │
│                  manufacturer · custom_field · tag · ci_tag                  │
└──┬──────────┬──────────────┬───────────────┬──────────────┬─────────────────┘
   │          │              │               │              │
   │  ┌───────▼──────┐ ┌─────▼────────┐ ┌────▼──────────┐ ┌─▼─────────────────┐
   │  │ NETWORK      │ │ DATACENTER   │ │ POWER         │ │ CATALOG           │
   │  │ interface    │ │ rack         │ │ power_node    │ │ service · sla     │
   │  │ connection   │ │ rack_mount   │ │ power_link    │ │ application · vm  │
   │  │ vlan·prefix  │ │ floorplan_*  │ │ power_scenario│ │ cluster · database│
   │  │ ip_address   │ │              │ │ *_computed    │ │ storage_system    │
   │  └──────────────┘ └──────────────┘ └───────────────┘ └───────────────────┘
   │
   │  ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌───────────────────┐
   ├─▶│ DNS          │ │ DOCS         │ │ PROJECTS      │ │ OPERATIONS        │
   │  │ domain       │ │ document     │ │ project·phase │ │ change            │
   │  │ dns_record   │ │ doc_version  │ │ task·milestone│ │ incident·problem  │
   │  │ certificate  │ │ file_object  │ │ dependency    │ │ maintenance_window│
   │  │ registrar    │ │ document_link│ │ time_entry    │ │ sla_timer         │
   │  └──────────────┘ └──────────────┘ └───────────────┘ └───────────────────┘
   │
   │  ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌───────────────────┐
   └─▶│ STATES       │ │ SEARCH       │ │ REPORTS       │ │ CORE              │
      │ state_snapshot│ │ search_index │ │ report_def    │ │ audit_log         │
      │ planned_change│ │              │ │ report_run    │ │ audit_change      │
      │ change_item   │ │              │ │ saved_filter  │ │ outbox·job        │
      └──────────────┘ └──────────────┘ └───────────────┘ └───────────────────┘

      ┌──────────────────────────────────────────────────────────────────────┐
      │ INTEGRATIONS (закладка): integration_source · import_job ·           │
      │ discovery_record · reconciliation_diff                               │
      └──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Перечень сущностей

### 2.1 DIRECTORY — организация и люди

| Сущность | Назначение | Основные связи |
|---|---|---|
| `organization` | Юрлицо / компания | → `department`, `location(ORG)` |
| `department` | Подразделение | → `employee`, `service.business_owner` |
| `employee` | Сотрудник (человек) | владелец/ответственный `ci`, исполнитель `task`, участник `project`, `responsibility_area` |
| `responsibility_area` | Зона ответственности как правило-фильтр | → `employee`, разворачивается в `ci[]` |
| `app_user` | Учётная запись (owner; позже — исполнители) | → `employee`, `session`, `role` |
| `role`, `permission`, `role_permission` | Модель прав (заложена, включается позже) | → `app_user` |
| `session` | Серверная сессия | → `app_user` |

### 2.2 CMDB — ядро графа

| Сущность | Назначение | Основные связи |
|---|---|---|
| `ci` | Базовый объект любого типа | ← все таблицы-расширения; → `ci_relation`, `document_link`, `task_ci`, `change_ci` |
| `ci_relation` | Логическое ребро графа | `ci` → `ci` |
| `location` | Узел физической иерархии (ORG/SITE/BUILDING/FLOOR/ROOM/ZONE) | самоссылка `parent_id`, → `ci.location_id` |
| `device` | Железо: сервер, коммутатор, firewall, AP, патч-панель, СХД | → `device_model`, `rack_mount`, `interface`, `power_node(PSU)` |
| `device_model` | Каталог моделей (габариты, вес, мощность, шаблон портов) | → `manufacturer`, `port_template` |
| `manufacturer` | Производитель | → `device_model` |
| `port_template` | Шаблон портов модели — автосоздание интерфейсов | → `device_model` |
| `custom_field` | Реестр произвольных полей | → `ci.attributes` |
| `tag`, `ci_tag` | Теги объектов | многие-ко-многим |
| `comment` | Комментарии к любому объекту | полиморфная привязка |

### 2.3 NETWORK — сетевая модель

| Сущность | Назначение | Основные связи |
|---|---|---|
| `interface` | Порт устройства (физический/логический/front/rear патч-панели) | → `ci` (владелец), `connection`, `ip_address`, `interface_vlan` |
| `connection` | Кабель/сегмент линии как самостоятельная сущность | `interface` A ↔ `interface` B |
| `cable_route` | Кабельная трасса (лоток, короб, трубостойка) | → `connection[]`, `location[]` |
| `vlan` | VLAN | → `prefix`, `interface_vlan`, `location`-scope |
| `vrf` | Виртуальный роутинг (для уникальности адресов) | → `prefix`, `ip_address` |
| `prefix` | Подсеть (cidr) | → `vlan`, `vrf`, `ip_address` |
| `ip_address` | Адрес | → `interface`, `prefix`, `ci` |
| `interface_vlan` | Access/trunk-членство | `interface` ↔ `vlan` |
| `wireless_ssid` | SSID (для AP) | → `device[]`, `vlan` |
| `circuit` | Внешний канал провайдера | → `provider`, `interface` |

### 2.4 DATACENTER — физика размещения

| Сущность | Назначение | Основные связи |
|---|---|---|
| `rack` | Стойка/шкаф 19" | → `location`, `rack_mount[]`, `power_node(PDU)[]` |
| `rack_mount` | Размещение устройства по U | `device` ↔ `rack` |
| `rack_reservation` | Резерв места под будущее оборудование | → `rack`, `project` |
| `floorplan` | План этажа/помещения | → `location` |
| `floorplan_item` | Объект на плане (координаты, поворот) | → `ci`, `floorplan` |

### 2.5 POWER — электрическая модель

| Сущность | Назначение | Основные связи |
|---|---|---|
| `power_node` | Узел: ввод, щит, автомат, линия, UPS, PDU, розетка, PSU | → `ci`, `power_link`, `location`/`rack` |
| `power_link` | Ребро питания (родитель → потребитель), фаза, номинал | `power_node` → `power_node` |
| `power_phase_load` | Расчётная нагрузка по фазам (кэш) | → `power_node` |
| `power_node_computed` | Расчёт нагрузки/резерва + трасса расчёта | → `power_node` |
| `power_scenario` | Сценарий «что если» | → `project`, `power_scenario_item[]` |
| `power_scenario_item` | Планируемое добавление/удаление/перенос нагрузки | → `power_node`, `device_model` |

### 2.6 CATALOG — сервисы и системы

| Сущность | Назначение | Основные связи |
|---|---|---|
| `service` | ИТ-сервис (1С, почта, VPN) | → `sla`, зависимости через `ci_relation`, `incident`, `document_link` |
| `sla` | Параметры SLA | → `service`, `sla_timer` |
| `application` | Приложение | → `virtual_machine`/`device` через `RUNS_ON` |
| `virtual_machine` | ВМ | → host (`device`), `cluster`, `storage_system` |
| `cluster` | Кластер | → узлы (`device[]`) |
| `database_instance` | Экземпляр СУБД | → `application`, host |
| `storage_system` | СХД | → `virtual_machine[]`, `device` |
| `backup_policy` | Политика резервного копирования | → `ci[]` |

### 2.7 DNS — домены и сертификаты

| Сущность | Назначение | Основные связи |
|---|---|---|
| `domain` | Домен/поддомен | → `registrar`, `dns_record[]`, `service` |
| `dns_record` | Запись (A, AAAA, CNAME, MX, TXT, SRV) | → `domain`, `ip_address` |
| `certificate` | TLS-сертификат | → `domain[]`, `service`, `ci[]` |
| `registrar` | Регистратор / DNS-провайдер | → `domain[]` |
| `renewal_watch` | Контроль сроков (домены, сертификаты, гарантии, лицензии) | полиморфная привязка |

### 2.8 DOCS — база знаний

| Сущность | Назначение | Основные связи |
|---|---|---|
| `document` | Документ (регламент, инструкция, схема, проектная документация) | → `document_version[]`, `document_link[]`, `folder` |
| `document_version` | Неизменяемая версия с телом и метаданными | → `document` |
| `document_link` | Привязка документа к любому объекту | `document` ↔ (`ci`\|`project`\|`task`\|`change`\|`service`) |
| `folder` | Иерархия папок базы знаний | самоссылка |
| `file_object` | Файл в MinIO (метаданные, sha256) | → `document_version`, `task`, `comment`, `change` |
| `document_approval` | Согласование/утверждение | → `document_version`, `employee` |
| `document_review` | График пересмотра | → `document`, `employee` |

### 2.9 PROJECTS — проектное управление

| Сущность | Назначение | Основные связи |
|---|---|---|
| `project` | Проект | → `phase[]`, `task[]`, `milestone[]`, `project_ci[]`, `state_snapshot`, `budget` |
| `phase` | Этап проекта | → `task[]` |
| `milestone` | Веха | → `task[]` |
| `task` | Универсальная задача (все типы) | → `project`, `phase`, `assignee`, `task_ci[]`, `task_dependency[]` |
| `task_dependency` | Зависимость задач (FS/SS/FF/SF) | `task` ↔ `task` |
| `task_ci` | Связь задачи с объектами инфраструктуры | `task` ↔ `ci` |
| `time_entry` | Учёт времени | → `task`, `employee` |
| `project_member` | Участник проекта и его роль | `project` ↔ `employee` |
| `project_risk` | Риск проекта | → `project` |
| `project_result` | Результат/artifact | → `project`, `document` |
| `budget_item` | Бюджетная строка (план/факт) | → `project` |
| `recurrence` | Определение повторяющейся работы | → `task` (порождает экземпляры) |

### 2.10 OPERATIONS — эксплуатация

| Сущность | Назначение | Основные связи |
|---|---|---|
| `change` | Изменение инфраструктуры | → `change_ci[]`, `task[]`, `project`, `planned_change` |
| `change_ci` | Затронутые объекты и характер воздействия | `change` ↔ `ci` |
| `change_approval` | Согласование изменения | → `change`, `employee` |
| `incident` | Инцидент (тип задачи + расширение) | → `service`, `ci[]`, `sla_timer` |
| `problem` | Проблема | → `incident[]`, `change` |
| `maintenance_window` | Окно плановых работ | → `ci[]`, `service[]`, `change` |
| `sla_timer` | Таймер реакции/решения | → `incident`, `sla` |

### 2.11 STATES — CURRENT → TARGET

| Сущность | Назначение | Основные связи |
|---|---|---|
| `state_snapshot` | Снимок текущего состояния подграфа | → `project`, содержимое в `jsonb` + контрольная сумма |
| `planned_change` | Набор планируемых изменений (TARGET STATE) | → `project`, `change_item[]` |
| `change_item` | Элементарная операция: create/update/delete/move | → тип сущности + payload `jsonb`, зависимости |
| `state_diff` | Рассчитанная разница CURRENT vs TARGET | → `project` |

### 2.12 CORE / SEARCH / REPORTS / INTEGRATIONS

| Сущность | Назначение |
|---|---|
| `audit_log`, `audit_change` | История «кто, что, когда, было → стало» |
| `outbox`, `domain_event` | Доменные события |
| `job` | Фоновая задача (отчёт, экспорт, пересчёт) |
| `notification` | Уведомления владельцу системы |
| `search_index` | Единый поисковый индекс (tsvector + trigram) |
| `saved_filter` | Сохранённый фильтр/представление |
| `report_definition` | Определение отчёта (источник, поля, фильтры, группировки) |
| `report_run` | Запуск отчёта и ссылка на файл экспорта |
| `integration_source` | Источник интеграции (заглушка) |
| `import_job`, `discovery_record`, `reconciliation_diff` | Импорт и сверка (заглушки) |

---

## 3. Карта ключевых связей

### 3.1 Физическая вертикаль

```
organization
   └─ location(SITE)
        └─ location(BUILDING)
             └─ location(FLOOR)
                  └─ location(ROOM)               ← серверная
                       └─ location(ZONE)          ← ряд/зона
                            └─ rack               ← стойка 19"
                                 └─ rack_mount    ← позиция U
                                      └─ device   ← оборудование
                                           ├─ interface[]      → connection
                                           └─ power_node(PSU)  → power_link
```

### 3.2 Сетевая горизонталь

```
device A ── interface A ──┐
                          ├── connection (тип, категория, длина, маркировка, трасса)
device B ── interface B ──┘

interface ── ip_address ── prefix ── vlan ── vrf
interface ── interface_vlan ── vlan
patch_panel: interface(front) ⇄ interface(rear)   ← сквозная трассировка линка
```

### 3.3 Электрическая вертикаль

```
power_node(INPUT, 20 кВт)
   └─ power_node(PANEL «ЩС-1»)
        └─ power_node(BREAKER C32, фаза L1)
             └─ power_node(LINE «Л-3», 5×6 мм²)
                  └─ power_node(UPS «APC 20k»)
                       └─ power_node(PDU «R2-PDU-A»)
                            └─ power_node(OUTLET «C13 #7»)
                                 └─ power_node(PSU «SRV-01 PSU1»)
                                      └─ device «SRV-01»
```

Сторона B дублирует цепочку (второй ввод/UPS/PDU) — это моделируется вторым путём в DAG с признаком `feed_side = B`.

### 3.4 Логическая вертикаль сервиса

```
service «1С»
   ├─ DEPENDS_ON → application «1С:Предприятие»
   │                    └─ RUNS_ON → virtual_machine «VM-1C-APP»
   │                                     └─ RUNS_ON → device «HV-01»
   │                                                     └─ MEMBER_OF → cluster «HV-CLUSTER»
   ├─ DEPENDS_ON → database_instance «MSSQL-1C»
   ├─ DEPENDS_ON → service «Active Directory»
   ├─ DEPENDS_ON → service «DNS»
   ├─ DEPENDS_ON → device «FW-EDGE-01»
   ├─ BACKED_UP_BY → backup_policy «Daily-1C»
   └─ document_link → регламент, инструкция восстановления, схема
```

### 3.5 Деятельность вокруг объекта

```
                       ┌──── task[]      (что сейчас делается)
                       ├──── change[]    (что меняется)
ci «SRV-01» ───────────┼──── project[]   (в каких проектах участвует)
                       ├──── document[]  (чем описан)
                       ├──── incident[]  (что ломалось)
                       └──── audit_log[] (как менялся)
```

---

## 4. Матрица «что с чем связано»

Строка — источник, столбец — цель. `R` = через `ci_relation`, `T` = типизированная таблица, `L` = таблица-связка.

| ↓ от / → к | ci | location | rack | interface | power_node | service | task | project | change | document |
|---|---|---|---|---|---|---|---|---|---|---|
| **ci** | R | T (`location_id`) | T (`rack_mount`) | T (`interface.ci_id`) | T (`power_node.ci_id`) | R | L (`task_ci`) | L (`project_ci`) | L (`change_ci`) | L (`document_link`) |
| **location** | T | T (parent) | T | — | T | — | L | L | L | L |
| **rack** | T | T | — | — | T (PDU) | — | L | L | L | L |
| **interface** | T | — | — | T (`connection`) | — | — | — | — | — | — |
| **power_node** | T | T | T | — | T (`power_link`) | — | L | L | L | L |
| **service** | R | — | — | — | — | R | L | L | L | L |
| **task** | L | — | — | — | — | L | T (`task_dependency`) | T | T | L |
| **project** | L | — | — | — | — | L | T | — | T | L |
| **change** | L | — | — | — | — | L | T | T | — | L |
| **document** | L | L | L | — | L | L | L | L | L | T (версии) |

---

## 5. Объёмы и характер данных (оценка для проектирования индексов)

| Сущность | Порядок количества | Особенности доступа |
|---|---|---|
| `ci` | 1 000 – 50 000 | Списки с фильтрами, полнотекстовый поиск |
| `interface` | 10 000 – 200 000 | Выборка по устройству; поиск по MAC/описанию |
| `connection` | 5 000 – 100 000 | Трассировка (рекурсивные обходы) |
| `ip_address` | 1 000 – 50 000 | Поиск по адресу/подсети (`inet` операторы) |
| `power_node` / `power_link` | 500 – 10 000 | Полный обход DAG при пересчёте |
| `task` | 1 000 – 100 000 | Kanban, списки, Gantt, агрегаты по сотрудникам |
| `document` / `document_version` | 100 – 10 000 | Поиск, пересмотры |
| `audit_log` | 100 000 – 5 000 000 | Только вставка и чтение по `(entity_type, entity_id)`; секционирование по месяцам |
| `search_index` | ≈ сумма сущностей | GIN по tsvector |
