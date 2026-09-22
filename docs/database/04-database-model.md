# 04 — Модель базы данных (PostgreSQL 16)

Документ описывает физическую схему: таблицы, ключи, ограничения, индексы, расширения и соглашения. DDL приведён в сокращённом виде — только значимые поля и ограничения; служебные поля (`created_at`, `updated_at`, `created_by`, `updated_by`, `version`) подразумеваются везде, где указан миксин.

## 1. Соглашения

| Правило | Значение |
|---|---|
| Именование таблиц | `snake_case`, единственное число (`ci`, `interface`, `power_node`) |
| Первичные ключи | `uuid` (`gen_random_uuid()` из `pgcrypto`), кроме журналов (`bigserial`) |
| Внешние ключи | Всегда объявлены, с явным `ON DELETE` (`RESTRICT` по умолчанию) |
| Временные метки | `timestamptz`, UTC |
| Мягкое удаление | `deleted_at timestamptz NULL` + частичные уникальные индексы `WHERE deleted_at IS NULL` |
| Оптимистическая блокировка | `version integer NOT NULL DEFAULT 1` |
| Перечисления | Нативные `CREATE TYPE ... AS ENUM` для стабильных наборов; `text` + справочная таблица для расширяемых |
| Денормализация | Только в таблицах `*_computed` с полем `computed_at` |
| Миграции | Alembic, одна миграция = одно логическое изменение, ручная правка автогенерации обязательна |

Служебные миксины:

```sql
-- TimestampMixin
created_at  timestamptz NOT NULL DEFAULT now(),
updated_at  timestamptz NOT NULL DEFAULT now(),
-- ActorMixin
created_by  uuid REFERENCES app_user(id) ON DELETE SET NULL,
updated_by  uuid REFERENCES app_user(id) ON DELETE SET NULL,
-- SoftDeleteMixin
deleted_at  timestamptz,
-- VersionMixin
version     integer NOT NULL DEFAULT 1
```

## 2. Расширения PostgreSQL

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- EXCLUDE-ограничения с равенством + диапазоном
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- поиск по подстроке: hostname, серийники, MAC
CREATE EXTENSION IF NOT EXISTS unaccent;    -- нормализация для FTS
```

Каждое расширение используется конкретной функцией системы, «на всякий случай» ничего не подключается.

---

## 3. Перечисления

```sql
CREATE TYPE ci_type AS ENUM (
  'LOCATION','RACK','DEVICE','VM','CLUSTER','APPLICATION','DATABASE',
  'SERVICE','STORAGE','POWER_NODE','DOMAIN','CERTIFICATE','CIRCUIT','OTHER');

CREATE TYPE ci_status AS ENUM (
  'PLANNED','ORDERED','IN_STOCK','ACTIVE','DEGRADED','MAINTENANCE',
  'RESERVED','DECOMMISSIONING','RETIRED');

CREATE TYPE criticality AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
CREATE TYPE environment AS ENUM ('PROD','TEST','DEV','DR');

CREATE TYPE location_type AS ENUM ('ORG','SITE','BUILDING','FLOOR','ROOM','ZONE');

CREATE TYPE device_role AS ENUM (
  'SERVER','ROUTER','L3_SWITCH','L2_SWITCH','FIREWALL','WIFI_AP','WIFI_CONTROLLER',
  'MODEM','PATCH_PANEL','WALL_PORT','STORAGE','KVM','UPS','PDU','PRINTER','OTHER');

CREATE TYPE interface_type AS ENUM (
  'RJ45','SFP','SFP_PLUS','SFP28','QSFP_PLUS','QSFP28','LC','SC','ST',
  'CONSOLE','USB','VIRTUAL','LAG','VLAN_IF','POWER','OTHER');

CREATE TYPE cable_medium AS ENUM ('COPPER','FIBER','DAC','AOC','POWER','OTHER');
CREATE TYPE cable_category AS ENUM (
  'CAT5E','CAT6','CAT6A','CAT7','CAT8','OM1','OM2','OM3','OM4','OM5','OS1','OS2','OTHER');
CREATE TYPE connection_status AS ENUM ('PLANNED','ACTIVE','RESERVED','FAULTY','DECOMMISSIONED');

CREATE TYPE power_node_type AS ENUM (
  'INPUT','PANEL','BREAKER','LINE','TRANSFER_SWITCH','UPS','PDU','OUTLET','PSU','GENERIC_LOAD');
CREATE TYPE feed_side AS ENUM ('A','B','SINGLE');
CREATE TYPE phase_label AS ENUM ('L1','L2','L3','L1L2L3');

CREATE TYPE task_type AS ENUM (
  'TASK','SUBTASK','INCIDENT','PROBLEM','REQUEST','MAINTENANCE','CHANGE_TASK');
CREATE TYPE task_status AS ENUM (
  'NEW','IN_PROGRESS','ON_HOLD','BLOCKED','REVIEW','DONE','CANCELLED');
CREATE TYPE priority AS ENUM ('LOW','MEDIUM','HIGH','URGENT','CRITICAL');

CREATE TYPE change_status AS ENUM (
  'DRAFT','SUBMITTED','APPROVED','REJECTED','SCHEDULED','IN_PROGRESS',
  'IMPLEMENTED','VERIFIED','CLOSED','ROLLED_BACK','FAILED');

CREATE TYPE document_status AS ENUM ('DRAFT','IN_REVIEW','APPROVED','OBSOLETE','ARCHIVED');
CREATE TYPE project_status AS ENUM ('DRAFT','PLANNING','IN_PROGRESS','ON_HOLD','COMPLETED','CANCELLED');
```

---

## 4. Directory

```sql
CREATE TABLE organization (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  inn text, address text, notes text
  -- + Timestamp, Actor, SoftDelete
);

CREATE TABLE department (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  parent_id uuid REFERENCES department(id) ON DELETE SET NULL,
  name text NOT NULL,
  head_employee_id uuid,
  UNIQUE (organization_id, name)
);

CREATE TABLE employee (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name text NOT NULL,
  position text,
  department_id uuid REFERENCES department(id) ON DELETE SET NULL,
  support_line smallint CHECK (support_line BETWEEN 0 AND 3),
  specializations text[] NOT NULL DEFAULT '{}',
  email citext, phone text, telegram text,
  is_active boolean NOT NULL DEFAULT true,
  weekly_capacity_hours numeric(5,2) NOT NULL DEFAULT 40,
  employed_from date, employed_to date
);
CREATE INDEX ix_employee_active ON employee(is_active) WHERE deleted_at IS NULL;
CREATE INDEX ix_employee_specializations ON employee USING gin (specializations);

CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid UNIQUE REFERENCES employee(id) ON DELETE SET NULL,
  login citext NOT NULL UNIQUE,
  password_hash text NOT NULL,          -- argon2id
  is_owner boolean NOT NULL DEFAULT false,
  is_active boolean NOT NULL DEFAULT true,
  last_login_at timestamptz
);

CREATE TABLE session (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,      -- sha256 от токена, сам токен не хранится
  csrf_token text NOT NULL,
  ip inet, user_agent text,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);

CREATE TABLE responsibility_area (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employee(id) ON DELETE CASCADE,
  name text NOT NULL,
  filter jsonb NOT NULL,                -- декларативный фильтр по CI
  is_primary boolean NOT NULL DEFAULT false
);
```

Модель прав (`role`, `permission`, `role_permission`, `user_role`) создаётся в Phase 1 и заполняется ролями `OWNER`, `ENGINEER`, `VIEWER`, но проверки применяются только к `OWNER` до включения многопользовательского режима.

---

## 5. CMDB

### 5.1 Базовая таблица CI

```sql
CREATE TABLE ci (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ci_type ci_type NOT NULL,
  name text NOT NULL,
  code text,
  status ci_status NOT NULL DEFAULT 'ACTIVE',
  criticality criticality NOT NULL DEFAULT 'MEDIUM',
  environment environment NOT NULL DEFAULT 'PROD',
  owner_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  responsible_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  location_id uuid REFERENCES location(id) ON DELETE SET NULL,
  description text NOT NULL DEFAULT '',
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_system text, external_id text,
  is_managed_externally boolean NOT NULL DEFAULT false,
  last_synced_at timestamptz,
  valid_from date, valid_to date,
  search_tsv tsvector
  -- + Timestamp, Actor, SoftDelete, Version
);

CREATE UNIQUE INDEX uq_ci_code ON ci(lower(code)) WHERE deleted_at IS NULL AND code IS NOT NULL;
CREATE INDEX ix_ci_type_status ON ci(ci_type, status) WHERE deleted_at IS NULL;
CREATE INDEX ix_ci_location ON ci(location_id) WHERE deleted_at IS NULL;
CREATE INDEX ix_ci_owner ON ci(owner_id);
CREATE INDEX ix_ci_no_owner ON ci(id) WHERE owner_id IS NULL AND deleted_at IS NULL;  -- отчёт «без владельца»
CREATE INDEX ix_ci_attributes ON ci USING gin (attributes jsonb_path_ops);
CREATE INDEX ix_ci_name_trgm ON ci USING gin (name gin_trgm_ops);
CREATE INDEX ix_ci_tsv ON ci USING gin (search_tsv);
CREATE UNIQUE INDEX uq_ci_external ON ci(source_system, external_id)
  WHERE source_system IS NOT NULL AND external_id IS NOT NULL;
```

### 5.2 Граф связей

```sql
CREATE TYPE relation_type AS ENUM (
  'DEPENDS_ON','RUNS_ON','MEMBER_OF','PART_OF','CONNECTED_TO','USES_STORAGE',
  'BACKED_UP_BY','REPLICATES_TO','MANAGES','SERVES','RELATES_TO');

CREATE TABLE ci_relation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,
  target_ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,
  rel_type relation_type NOT NULL,
  criticality criticality NOT NULL DEFAULT 'MEDIUM',
  description text NOT NULL DEFAULT '',
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from date, valid_to date,
  CONSTRAINT ck_relation_not_self CHECK (source_ci_id <> target_ci_id),
  CONSTRAINT uq_relation UNIQUE (source_ci_id, target_ci_id, rel_type)
);
CREATE INDEX ix_relation_source ON ci_relation(source_ci_id, rel_type);
CREATE INDEX ix_relation_target ON ci_relation(target_ci_id, rel_type);
```

Отсутствие циклов в `DEPENDS_ON` проверяется доменным сервисом рекурсивным CTE перед вставкой (в БД это не выражается ограничением).

### 5.3 Локации

```sql
CREATE TABLE location (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,   -- joined-table inheritance
  location_type location_type NOT NULL,
  parent_id uuid REFERENCES location(id) ON DELETE RESTRICT,
  path text NOT NULL,                     -- материализованный путь: 'org/site-1/bld-a/fl-2/room-3'
  depth smallint NOT NULL DEFAULT 0,
  address text, floor_number smallint, area_m2 numeric(8,2),
  plan_width_mm integer, plan_height_mm integer,
  CONSTRAINT ck_location_parent CHECK (parent_id <> id)
);
CREATE UNIQUE INDEX uq_location_path ON location(path);
CREATE INDEX ix_location_parent ON location(parent_id);
CREATE INDEX ix_location_path_prefix ON location(path text_pattern_ops);  -- поддерево: path LIKE 'org/site-1/%'
```

Материализованный путь поддерживается триггером при смене `parent_id` (вместе с пересчётом путей потомков в одной транзакции). Выбор в пользу пути, а не рекурсивного CTE на каждый запрос: дерево мелкое (≤ 6 уровней), а запросы «всё в этом здании» выполняются постоянно.

### 5.4 Каталог оборудования

```sql
CREATE TABLE manufacturer (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE, support_url text, notes text);

CREATE TABLE device_model (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  manufacturer_id uuid NOT NULL REFERENCES manufacturer(id) ON DELETE RESTRICT,
  model text NOT NULL,
  part_number text,
  default_role device_role NOT NULL DEFAULT 'OTHER',
  u_height numeric(3,1) NOT NULL DEFAULT 1,      -- 0.5 для half-U, 0 для не-стоечного
  is_full_depth boolean NOT NULL DEFAULT true,
  depth_mm integer, weight_kg numeric(6,2),
  psu_count smallint NOT NULL DEFAULT 1,
  power_draw_w integer,          -- типовое потребление
  power_max_w integer,           -- максимальное (шильдик)
  airflow text,
  UNIQUE (manufacturer_id, model)
);

CREATE TABLE port_template (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_model_id uuid NOT NULL REFERENCES device_model(id) ON DELETE CASCADE,
  name_pattern text NOT NULL,        -- 'Gi1/0/{n}'
  count smallint NOT NULL,
  start_index smallint NOT NULL DEFAULT 1,
  interface_type interface_type NOT NULL,
  speed_mbps integer, poe_capable boolean NOT NULL DEFAULT false
);
```

### 5.5 Устройство

```sql
CREATE TABLE device (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  device_model_id uuid REFERENCES device_model(id) ON DELETE RESTRICT,
  device_role device_role NOT NULL,
  serial_number text, asset_tag text,
  hostname text, mgmt_ip inet, mgmt_mac macaddr,
  firmware text, os_version text,
  purchase_date date, warranty_until date,
  psu_count smallint NOT NULL DEFAULT 1,
  power_draw_w integer,               -- переопределяет модель, если измерено
  notes text
);
CREATE UNIQUE INDEX uq_device_serial ON device(lower(serial_number)) WHERE serial_number IS NOT NULL;
CREATE INDEX ix_device_hostname_trgm ON device USING gin (hostname gin_trgm_ops);
CREATE INDEX ix_device_mgmt_ip ON device(mgmt_ip);
CREATE INDEX ix_device_role ON device(device_role);
```

---

## 6. Network

### 6.1 Интерфейсы

```sql
CREATE TABLE interface (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,   -- владелец: device
  name text NOT NULL,
  position integer,                    -- номер порта для сортировки
  interface_type interface_type NOT NULL,
  medium cable_medium,
  speed_mbps integer,
  duplex text,
  mac macaddr,
  description text NOT NULL DEFAULT '',
  purpose text,                        -- 'uplink to core', 'iLO', 'СКУД'
  admin_enabled boolean NOT NULL DEFAULT true,
  oper_status text NOT NULL DEFAULT 'UNKNOWN',
  is_management boolean NOT NULL DEFAULT false,
  poe_mode text,
  mtu integer,
  lag_parent_id uuid REFERENCES interface(id) ON DELETE SET NULL,
  -- патч-панель: сопряжение front ⇄ rear
  panel_side text CHECK (panel_side IN ('FRONT','REAR')),
  paired_interface_id uuid REFERENCES interface(id) ON DELETE SET NULL,
  UNIQUE (ci_id, name)
);
CREATE INDEX ix_interface_ci ON interface(ci_id, position);
CREATE INDEX ix_interface_mac ON interface(mac);
CREATE INDEX ix_interface_desc_trgm ON interface USING gin (description gin_trgm_ops);
```

### 6.2 Соединения

```sql
CREATE TABLE connection (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label text,
  medium cable_medium NOT NULL,
  category cable_category,
  connector_a text, connector_b text,
  a_interface_id uuid NOT NULL REFERENCES interface(id) ON DELETE CASCADE,
  b_interface_id uuid NOT NULL REFERENCES interface(id) ON DELETE CASCADE,
  length_m numeric(6,2),
  speed_mbps integer,
  color text,
  status connection_status NOT NULL DEFAULT 'ACTIVE',
  route_id uuid REFERENCES cable_route(id) ON DELETE SET NULL,
  is_redundant boolean NOT NULL DEFAULT false,
  redundancy_group text,
  installed_on date, tested_on date, test_result text,
  description text NOT NULL DEFAULT '',
  CONSTRAINT ck_connection_distinct CHECK (a_interface_id <> b_interface_id)
);
-- один активный кабель на интерфейс (с каждой стороны)
CREATE UNIQUE INDEX uq_connection_a ON connection(a_interface_id)
  WHERE status IN ('ACTIVE','RESERVED');
CREATE UNIQUE INDEX uq_connection_b ON connection(b_interface_id)
  WHERE status IN ('ACTIVE','RESERVED');
CREATE INDEX ix_connection_label_trgm ON connection USING gin (label gin_trgm_ops);

CREATE TABLE cable_route (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  route_type text,                    -- лоток, короб, гофра, межэтажный стояк
  from_location_id uuid REFERENCES location(id),
  to_location_id uuid REFERENCES location(id),
  length_m numeric(6,2), capacity integer, notes text
);
```

Сквозная трассировка линка (через патч-панели) не хранится, а вычисляется рекурсивным CTE по парам `paired_interface_id` → `connection` и кэшируется в `link_path_computed` при изменении соединений.

### 6.3 Адресация

```sql
CREATE TABLE vrf (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE, rd text, description text);

CREATE TABLE vlan (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vid integer NOT NULL CHECK (vid BETWEEN 1 AND 4094),
  name text NOT NULL,
  site_id uuid REFERENCES location(id) ON DELETE SET NULL,
  purpose text, description text,
  UNIQUE (site_id, vid)
);

CREATE TABLE prefix (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cidr cidr NOT NULL,
  vrf_id uuid REFERENCES vrf(id) ON DELETE SET NULL,
  vlan_id uuid REFERENCES vlan(id) ON DELETE SET NULL,
  gateway inet,
  dhcp_from inet, dhcp_to inet,
  site_id uuid REFERENCES location(id) ON DELETE SET NULL,
  description text,
  UNIQUE (vrf_id, cidr)
);
CREATE INDEX ix_prefix_cidr ON prefix USING gist (cidr inet_ops);

CREATE TABLE ip_address (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  address inet NOT NULL,
  vrf_id uuid REFERENCES vrf(id) ON DELETE SET NULL,
  prefix_id uuid REFERENCES prefix(id) ON DELETE SET NULL,
  interface_id uuid REFERENCES interface(id) ON DELETE SET NULL,
  ci_id uuid REFERENCES ci(id) ON DELETE SET NULL,     -- если адрес закреплён за объектом без интерфейса
  dns_name text, role text, status text NOT NULL DEFAULT 'ACTIVE',
  description text
);
CREATE UNIQUE INDEX uq_ip_per_vrf ON ip_address(vrf_id, address) WHERE status <> 'DEPRECATED';
CREATE INDEX ix_ip_address ON ip_address USING gist (address inet_ops);
CREATE INDEX ix_ip_interface ON ip_address(interface_id);

CREATE TABLE interface_vlan (
  interface_id uuid NOT NULL REFERENCES interface(id) ON DELETE CASCADE,
  vlan_id uuid NOT NULL REFERENCES vlan(id) ON DELETE CASCADE,
  mode text NOT NULL CHECK (mode IN ('ACCESS','TAGGED','NATIVE')),
  PRIMARY KEY (interface_id, vlan_id)
);
```

---

## 7. Datacenter: стойки и размещение

```sql
CREATE TABLE rack (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  u_height smallint NOT NULL DEFAULT 42 CHECK (u_height BETWEEN 1 AND 60),
  width_in smallint NOT NULL DEFAULT 19,
  depth_mm integer NOT NULL DEFAULT 1000,
  max_weight_kg numeric(7,2),
  max_power_w integer,
  form_factor text NOT NULL DEFAULT 'CABINET',    -- CABINET | OPEN_FRAME | WALL
  descending_units boolean NOT NULL DEFAULT false,
  plan_x numeric(8,2), plan_y numeric(8,2), plan_rotation smallint NOT NULL DEFAULT 0
);

CREATE TABLE rack_mount (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rack_id uuid NOT NULL REFERENCES rack(id) ON DELETE CASCADE,
  ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,   -- device | pdu | patch panel
  position_u smallint NOT NULL CHECK (position_u >= 1),
  u_height smallint NOT NULL CHECK (u_height >= 1),
  face text NOT NULL DEFAULT 'FRONT' CHECK (face IN ('FRONT','REAR','FULL')),
  depth_mm integer,
  weight_kg numeric(6,2),
  is_reservation boolean NOT NULL DEFAULT false,
  project_id uuid REFERENCES project(id) ON DELETE SET NULL,  -- для планируемого размещения
  u_range int4range GENERATED ALWAYS AS
    (int4range(position_u, position_u + u_height)) STORED,
  CONSTRAINT uq_mount_ci UNIQUE (ci_id)
);

-- Физический инвариант: оборудование не может перекрываться по U на одном фасаде.
-- FULL занимает оба фасада, поэтому конфликтует и с FRONT, и с REAR.
ALTER TABLE rack_mount ADD CONSTRAINT ex_rack_mount_overlap
  EXCLUDE USING gist (
    rack_id WITH =,
    u_range WITH &&,
    face WITH <>       -- см. примечание
  ) WHERE (is_reservation = false);
```

> **Примечание к ограничению.** Оператор `<>` в `EXCLUDE` недоступен для text напрямую; реализация использует нормализацию фасада в два булевых поля `occupies_front`, `occupies_rear` (генерируемые из `face`) и два ограничения `EXCLUDE ... WHERE (occupies_front)` и `EXCLUDE ... WHERE (occupies_rear)`. Это даёт корректную семантику: FULL конфликтует с обоими фасадами, FRONT — только с FRONT. Проверка «не выходит за пределы стойки» (`position_u + u_height - 1 ≤ rack.u_height`) выполняется триггером, так как требует обращения к родительской таблице.

Резервирования (`is_reservation = true`) исключены из ограничения намеренно: план может конфликтовать с текущим размещением — конфликт показывается как предупреждение в проекте, а не как ошибка БД.

```sql
CREATE TABLE floorplan (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id uuid NOT NULL REFERENCES location(id) ON DELETE CASCADE,
  name text NOT NULL, width_mm integer NOT NULL, height_mm integer NOT NULL,
  background_file_id uuid REFERENCES file_object(id) ON DELETE SET NULL,
  scale_px_per_m numeric(8,3));

CREATE TABLE floorplan_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  floorplan_id uuid NOT NULL REFERENCES floorplan(id) ON DELETE CASCADE,
  ci_id uuid REFERENCES ci(id) ON DELETE CASCADE,
  item_kind text NOT NULL,          -- RACK | DEVICE | POWER | ANNOTATION | ROUTE
  x numeric(9,2) NOT NULL, y numeric(9,2) NOT NULL,
  width numeric(9,2), height numeric(9,2), rotation smallint NOT NULL DEFAULT 0,
  label text, style jsonb NOT NULL DEFAULT '{}'::jsonb);
```

---

## 8. Power

```sql
CREATE TABLE power_node (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  node_type power_node_type NOT NULL,
  parent_device_id uuid REFERENCES ci(id) ON DELETE CASCADE,  -- для PSU: чей блок питания
  rack_id uuid REFERENCES rack(id) ON DELETE SET NULL,
  feed_side feed_side NOT NULL DEFAULT 'SINGLE',
  voltage_v numeric(6,1),
  phases smallint NOT NULL DEFAULT 1 CHECK (phases IN (1,3)),
  phase_label phase_label,
  rated_power_w integer,            -- номинал/шильдик
  rated_current_a numeric(7,2),     -- номинал автомата/линии
  power_factor numeric(4,3),        -- cos φ
  efficiency numeric(4,3),          -- КПД (UPS, PSU)
  max_load_w integer,               -- предельно допустимая нагрузка
  derating_factor numeric(4,3) NOT NULL DEFAULT 0.8,  -- для автоматов: длительная нагрузка
  measured_load_w integer,          -- фактическое измерение, если есть
  ups_capacity_va integer, ups_battery_minutes smallint,
  outlet_type text,                 -- C13, C19, Schuko
  outlet_count smallint,
  notes text
);
CREATE INDEX ix_power_node_type ON power_node(node_type);
CREATE INDEX ix_power_node_rack ON power_node(rack_id);

CREATE TABLE power_link (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_node_id uuid NOT NULL REFERENCES power_node(id) ON DELETE CASCADE,  -- питающий
  target_node_id uuid NOT NULL REFERENCES power_node(id) ON DELETE CASCADE,  -- потребитель
  phase_label phase_label,
  rated_current_a numeric(7,2),
  cable_spec text,                  -- '5×6 мм², ВВГнг'
  length_m numeric(6,2),
  status connection_status NOT NULL DEFAULT 'ACTIVE',
  outlet_number text,
  CONSTRAINT ck_power_link_distinct CHECK (source_node_id <> target_node_id),
  CONSTRAINT uq_power_link UNIQUE (source_node_id, target_node_id)
);
CREATE INDEX ix_power_link_source ON power_link(source_node_id);
CREATE INDEX ix_power_link_target ON power_link(target_node_id);

-- Результаты расчёта: значения + объяснение
CREATE TABLE power_node_computed (
  node_id uuid PRIMARY KEY REFERENCES power_node(id) ON DELETE CASCADE,
  scenario_id uuid REFERENCES power_scenario(id) ON DELETE CASCADE,
  connected_load_w integer NOT NULL DEFAULT 0,     -- сумма шильдиков потомков
  estimated_load_w integer NOT NULL DEFAULT 0,     -- расчётная (с коэффициентами)
  measured_load_w integer,
  load_by_phase jsonb NOT NULL DEFAULT '{}'::jsonb,
  utilisation numeric(5,2),                        -- % от max_load_w
  headroom_w integer,
  redundancy_ok boolean,
  calculation_trace jsonb NOT NULL DEFAULT '[]'::jsonb,  -- шаги расчёта
  computed_at timestamptz NOT NULL DEFAULT now(),
  formula_version smallint NOT NULL DEFAULT 1
);

CREATE TABLE power_scenario (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid REFERENCES project(id) ON DELETE CASCADE,
  name text NOT NULL,
  base_snapshot_id uuid REFERENCES state_snapshot(id) ON DELETE SET NULL,
  description text, is_applied boolean NOT NULL DEFAULT false);

CREATE TABLE power_scenario_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES power_scenario(id) ON DELETE CASCADE,
  operation text NOT NULL CHECK (operation IN ('ADD','REMOVE','MODIFY','MOVE')),
  target_node_id uuid REFERENCES power_node(id) ON DELETE CASCADE,
  attach_to_node_id uuid REFERENCES power_node(id) ON DELETE CASCADE,
  device_model_id uuid REFERENCES device_model(id) ON DELETE SET NULL,
  quantity smallint NOT NULL DEFAULT 1,
  power_w integer, phases smallint, feed_side feed_side,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text);
```

---

## 9. Catalog: сервисы и системы

```sql
CREATE TABLE sla (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  availability_target numeric(5,3),      -- 99.900
  response_minutes integer, resolution_minutes integer,
  service_hours text,                    -- '24x7' | '8x5'
  penalty_notes text);

CREATE TABLE service (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  category text NOT NULL,
  sla_id uuid REFERENCES sla(id) ON DELETE SET NULL,
  business_owner_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  department_id uuid REFERENCES department(id) ON DELETE SET NULL,
  rto_minutes integer, rpo_minutes integer,
  users_count integer, url text);

CREATE TABLE application (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  app_type text, vendor text, version text, runtime text, url text,
  license_until date, license_notes text);

CREATE TABLE virtual_machine (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  host_ci_id uuid REFERENCES ci(id) ON DELETE SET NULL,
  cluster_id uuid REFERENCES cluster(id) ON DELETE SET NULL,
  vcpu smallint, ram_mb integer, disk_gb integer,
  guest_os text, hypervisor text, vm_uuid text);

CREATE TABLE cluster (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  cluster_type text, ha_policy text, node_count smallint);

CREATE TABLE database_instance (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  engine text NOT NULL, engine_version text, port integer,
  size_gb numeric(10,2), backup_policy_id uuid REFERENCES backup_policy(id));

CREATE TABLE storage_system (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  capacity_tb numeric(8,2), used_tb numeric(8,2), protocol text, raid_level text);

CREATE TABLE backup_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL, schedule text, retention text, target text, notes text);
```

---

## 10. DNS, домены, сертификаты

```sql
CREATE TABLE registrar (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE, portal_url text, account text, notes text);

CREATE TABLE domain (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  fqdn text NOT NULL, parent_domain_id uuid REFERENCES domain(id) ON DELETE SET NULL,
  registrar_id uuid REFERENCES registrar(id) ON DELETE SET NULL,
  dns_provider text, registered_on date, expires_on date,
  auto_renew boolean NOT NULL DEFAULT false);
CREATE UNIQUE INDEX uq_domain_fqdn ON domain(lower(fqdn));
CREATE INDEX ix_domain_expires ON domain(expires_on);

CREATE TABLE dns_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id uuid NOT NULL REFERENCES domain(id) ON DELETE CASCADE,
  name text NOT NULL, record_type text NOT NULL, value text NOT NULL,
  ttl integer, priority integer,
  ip_address_id uuid REFERENCES ip_address(id) ON DELETE SET NULL,
  managed_externally boolean NOT NULL DEFAULT false);
CREATE INDEX ix_dns_record_domain ON dns_record(domain_id, record_type);

CREATE TABLE certificate (
  id uuid PRIMARY KEY REFERENCES ci(id) ON DELETE CASCADE,
  common_name text NOT NULL, sans text[] NOT NULL DEFAULT '{}',
  issuer text, serial text, key_type text, key_size integer,
  valid_from date, valid_to date NOT NULL,
  auto_renew boolean NOT NULL DEFAULT false,
  private_key_location text);           -- ссылка на расположение, сам ключ не хранится
CREATE INDEX ix_certificate_valid_to ON certificate(valid_to);
```

---

## 11. Документы и файлы

```sql
CREATE TABLE folder (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id uuid REFERENCES folder(id) ON DELETE CASCADE,
  name text NOT NULL, path text NOT NULL,
  UNIQUE (parent_id, name));

CREATE TABLE document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text UNIQUE,                       -- DOC-0042
  title text NOT NULL,
  doc_type text NOT NULL,                 -- REGULATION | INSTRUCTION | POLICY | STANDARD |
                                          -- ARCHITECTURE | OPERATIONS | PROJECT | DIAGRAM | TEMPLATE | OTHER
  status document_status NOT NULL DEFAULT 'DRAFT',
  folder_id uuid REFERENCES folder(id) ON DELETE SET NULL,
  author_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  owner_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  current_version_id uuid,
  review_period_months smallint,
  review_due_on date,
  tags text[] NOT NULL DEFAULT '{}',
  search_tsv tsvector);
CREATE INDEX ix_document_review_due ON document(review_due_on) WHERE deleted_at IS NULL;
CREATE INDEX ix_document_tags ON document USING gin (tags);
CREATE INDEX ix_document_tsv ON document USING gin (search_tsv);

CREATE TABLE document_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  version_number integer NOT NULL,
  body_md text NOT NULL DEFAULT '',
  summary text,
  author_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  file_id uuid REFERENCES file_object(id) ON DELETE SET NULL,   -- если документ — файл
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_number));

CREATE TABLE document_link (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  entity_type text NOT NULL,      -- ci | project | task | change | service | incident
  entity_id uuid NOT NULL,
  link_role text,                 -- 'схема', 'инструкция', 'акт'
  UNIQUE (document_id, entity_type, entity_id));
CREATE INDEX ix_document_link_entity ON document_link(entity_type, entity_id);

CREATE TABLE file_object (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket text NOT NULL, object_key text NOT NULL,
  filename text NOT NULL, mime_type text NOT NULL,
  size_bytes bigint NOT NULL, sha256 text NOT NULL,
  uploaded_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
  entity_type text, entity_id uuid,
  UNIQUE (bucket, object_key));
CREATE INDEX ix_file_entity ON file_object(entity_type, entity_id);
CREATE INDEX ix_file_sha ON file_object(sha256);
```

---

## 12. Проекты и задачи

```sql
CREATE TABLE project (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,                -- 'PWR'
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  status project_status NOT NULL DEFAULT 'PLANNING',
  priority priority NOT NULL DEFAULT 'MEDIUM',
  owner_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  start_date date, due_date date,
  actual_start_date date, actual_end_date date,
  budget_planned numeric(14,2), budget_actual numeric(14,2),
  progress_pct numeric(5,2) NOT NULL DEFAULT 0,
  task_seq integer NOT NULL DEFAULT 0);

CREATE TABLE phase (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name text NOT NULL, order_index smallint NOT NULL DEFAULT 0,
  start_date date, end_date date, status text NOT NULL DEFAULT 'PLANNED');

CREATE TABLE milestone (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name text NOT NULL, due_date date, status text NOT NULL DEFAULT 'PLANNED',
  completed_at timestamptz, description text);

CREATE TABLE task (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  number integer NOT NULL,
  project_id uuid REFERENCES project(id) ON DELETE CASCADE,
  phase_id uuid REFERENCES phase(id) ON DELETE SET NULL,
  milestone_id uuid REFERENCES milestone(id) ON DELETE SET NULL,
  parent_id uuid REFERENCES task(id) ON DELETE CASCADE,
  task_type task_type NOT NULL DEFAULT 'TASK',
  title text NOT NULL, description text NOT NULL DEFAULT '',
  status task_status NOT NULL DEFAULT 'NEW',
  priority priority NOT NULL DEFAULT 'MEDIUM',
  assignee_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  reporter_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  service_id uuid REFERENCES service(id) ON DELETE SET NULL,
  change_id uuid REFERENCES change(id) ON DELETE SET NULL,
  start_date date, due_date date,
  estimate_min integer NOT NULL DEFAULT 0,
  spent_min integer NOT NULL DEFAULT 0,
  completed_at timestamptz,
  recurrence_id uuid REFERENCES recurrence(id) ON DELETE SET NULL,
  order_index numeric(12,4) NOT NULL DEFAULT 0,
  UNIQUE (project_id, number));
CREATE INDEX ix_task_status_due ON task(status, due_date) WHERE deleted_at IS NULL;
CREATE INDEX ix_task_assignee ON task(assignee_id, status) WHERE deleted_at IS NULL;
CREATE INDEX ix_task_project ON task(project_id, status);
CREATE INDEX ix_task_overdue ON task(due_date)
  WHERE status NOT IN ('DONE','CANCELLED') AND deleted_at IS NULL;

CREATE TABLE task_dependency (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  predecessor_id uuid NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  successor_id uuid NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  dep_kind text NOT NULL DEFAULT 'FS' CHECK (dep_kind IN ('FS','SS','FF','SF')),
  lag_days smallint NOT NULL DEFAULT 0,
  CONSTRAINT ck_dep_distinct CHECK (predecessor_id <> successor_id),
  UNIQUE (predecessor_id, successor_id));

CREATE TABLE task_ci (
  task_id uuid NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,
  role text,                   -- 'объект работ' | 'затронут' | 'источник проблемы'
  PRIMARY KEY (task_id, ci_id));

CREATE TABLE project_ci (
  project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,
  involvement text,            -- 'изменяется' | 'создаётся' | 'выводится' | 'затронут'
  PRIMARY KEY (project_id, ci_id));

CREATE TABLE time_entry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employee(id) ON DELETE CASCADE,
  work_date date NOT NULL, minutes integer NOT NULL CHECK (minutes > 0),
  note text);
CREATE INDEX ix_time_entry_emp_date ON time_entry(employee_id, work_date);

CREATE TABLE recurrence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL, project_id uuid REFERENCES project(id) ON DELETE CASCADE,
  task_type task_type NOT NULL DEFAULT 'MAINTENANCE',
  freq text NOT NULL, interval_n smallint NOT NULL DEFAULT 1,
  weekdays smallint[], day_of_month smallint,
  assignee_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  estimate_min integer NOT NULL DEFAULT 0,
  lead_days smallint NOT NULL DEFAULT 0,
  next_run_on date, last_spawned_at timestamptz,
  is_active boolean NOT NULL DEFAULT true,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb);
```

---

## 13. Эксплуатация и изменения

```sql
CREATE TABLE change (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,                 -- CHG-0031
  title text NOT NULL, description text NOT NULL DEFAULT '',
  reason text NOT NULL DEFAULT '',
  change_kind text NOT NULL DEFAULT 'NORMAL' CHECK (change_kind IN ('STANDARD','NORMAL','EMERGENCY')),
  status change_status NOT NULL DEFAULT 'DRAFT',
  risk_level criticality NOT NULL DEFAULT 'MEDIUM',
  impact text,
  initiator_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  implementer_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  project_id uuid REFERENCES project(id) ON DELETE SET NULL,
  planned_window tstzrange,
  actual_window tstzrange,
  plan_md text, rollback_md text, validation_md text, result_md text,
  outcome text CHECK (outcome IN ('SUCCESS','PARTIAL','FAILED','ROLLED_BACK')),
  planned_change_id uuid REFERENCES planned_change(id) ON DELETE SET NULL);
CREATE INDEX ix_change_status ON change(status);
CREATE INDEX ix_change_window ON change USING gist (planned_window);

CREATE TABLE change_ci (
  change_id uuid NOT NULL REFERENCES change(id) ON DELETE CASCADE,
  ci_id uuid NOT NULL REFERENCES ci(id) ON DELETE CASCADE,
  impact text NOT NULL DEFAULT 'AFFECTED',   -- AFFECTED | MODIFIED | CREATED | REMOVED | DOWNTIME
  PRIMARY KEY (change_id, ci_id));

CREATE TABLE change_approval (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id uuid NOT NULL REFERENCES change(id) ON DELETE CASCADE,
  approver_id uuid REFERENCES employee(id) ON DELETE SET NULL,
  external_party text,                        -- например, управляющая компания
  decision text CHECK (decision IN ('PENDING','APPROVED','REJECTED')),
  decided_at timestamptz, comment text, document_id uuid REFERENCES document(id));

CREATE TABLE incident (
  id uuid PRIMARY KEY REFERENCES task(id) ON DELETE CASCADE,   -- расширение task
  service_id uuid REFERENCES service(id) ON DELETE SET NULL,
  severity criticality NOT NULL DEFAULT 'MEDIUM',
  detected_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz, downtime_minutes integer,
  root_cause text, problem_id uuid REFERENCES problem(id) ON DELETE SET NULL);

CREATE TABLE problem (
  id uuid PRIMARY KEY REFERENCES task(id) ON DELETE CASCADE,
  root_cause text, workaround text, permanent_fix_change_id uuid REFERENCES change(id));

CREATE TABLE maintenance_window (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL, window_range tstzrange NOT NULL,
  change_id uuid REFERENCES change(id) ON DELETE SET NULL,
  notify_before_hours smallint, notes text);
CREATE INDEX ix_maintenance_range ON maintenance_window USING gist (window_range);

CREATE TABLE sla_timer (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incident(id) ON DELETE CASCADE,
  sla_id uuid REFERENCES sla(id) ON DELETE SET NULL,
  timer_kind text NOT NULL CHECK (timer_kind IN ('RESPONSE','RESOLUTION')),
  started_at timestamptz NOT NULL, due_at timestamptz NOT NULL,
  stopped_at timestamptz, breached boolean NOT NULL DEFAULT false);
```

---

## 14. Состояния: CURRENT → TARGET

```sql
CREATE TABLE state_snapshot (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid REFERENCES project(id) ON DELETE CASCADE,
  name text NOT NULL, scope jsonb NOT NULL,      -- что вошло в снимок (фильтр)
  payload jsonb NOT NULL,                        -- нормализованный подграф
  checksum text NOT NULL,
  taken_at timestamptz NOT NULL DEFAULT now(),
  taken_by uuid REFERENCES app_user(id));

CREATE TABLE planned_change (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name text NOT NULL,
  base_snapshot_id uuid REFERENCES state_snapshot(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT','REVIEW','APPROVED','APPLYING','APPLIED','CANCELLED')),
  applied_at timestamptz);

CREATE TABLE change_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  planned_change_id uuid NOT NULL REFERENCES planned_change(id) ON DELETE CASCADE,
  operation text NOT NULL CHECK (operation IN ('CREATE','UPDATE','DELETE','MOVE','CONNECT','DISCONNECT')),
  entity_type text NOT NULL,          -- ci | device | rack_mount | connection | power_link | ip_address
  entity_id uuid,                     -- NULL для CREATE
  payload jsonb NOT NULL,             -- целевое состояние
  depends_on uuid[] NOT NULL DEFAULT '{}',
  order_index integer NOT NULL DEFAULT 0,
  apply_status text NOT NULL DEFAULT 'PENDING'
    CHECK (apply_status IN ('PENDING','APPLIED','SKIPPED','FAILED')),
  applied_entity_id uuid, error text);
CREATE INDEX ix_change_item_plan ON change_item(planned_change_id, order_index);
```

---

## 15. Аудит

```sql
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  actor_kind text NOT NULL DEFAULT 'USER' CHECK (actor_kind IN ('USER','SYSTEM','IMPORT','JOB')),
  request_id uuid,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  entity_label text,
  action text NOT NULL,          -- CREATE | UPDATE | DELETE | RESTORE | LINK | UNLINK | STATUS | APPLY
  change_id uuid REFERENCES change(id) ON DELETE SET NULL,
  comment text,
  source text                     -- api | ui | job | import
) PARTITION BY RANGE (occurred_at);

CREATE INDEX ix_audit_entity ON audit_log(entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_audit_actor ON audit_log(actor_id, occurred_at DESC);

CREATE TABLE audit_change (
  id bigserial PRIMARY KEY,
  audit_log_id bigint NOT NULL,
  field text NOT NULL,
  old_value jsonb, new_value jsonb);
CREATE INDEX ix_audit_change_log ON audit_change(audit_log_id);
```

Секционирование `audit_log` по месяцам: журнал растёт быстрее всех таблиц, а запросы почти всегда ограничены сущностью и периодом. Партиции создаёт фоновая задача на квартал вперёд. Права: у приложения нет `UPDATE`/`DELETE` на `audit_log` и `audit_change` — история неизменяема на уровне СУБД.

---

## 16. Поиск

```sql
CREATE TABLE search_index (
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  title text NOT NULL,
  subtitle text NOT NULL DEFAULT '',
  body text NOT NULL DEFAULT '',
  keywords text NOT NULL DEFAULT '',     -- hostname, IP, MAC, серийники, номера портов
  tags text[] NOT NULL DEFAULT '{}',
  location_path text,
  tsv tsvector NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_type, entity_id));

CREATE INDEX ix_search_tsv ON search_index USING gin (tsv);
CREATE INDEX ix_search_keywords_trgm ON search_index USING gin (keywords gin_trgm_ops);
CREATE INDEX ix_search_title_trgm ON search_index USING gin (title gin_trgm_ops);
```

Конфигурация FTS: `russian` + `unaccent`, для технических полей — отдельный вес. Веса: `A` — имя/код, `B` — hostname/IP/серийник, `C` — описание, `D` — тело документа. Индекс обновляется обработчиком доменных событий (в воркере), а не триггером — чтобы формировать `keywords` из связанных таблиц (IP, MAC, порты) одним местом.

---

## 17. Служебные таблицы

```sql
CREATE TABLE outbox (
  id bigserial PRIMARY KEY,
  event_type text NOT NULL, payload jsonb NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz, attempts smallint NOT NULL DEFAULT 0, error text);
CREATE INDEX ix_outbox_pending ON outbox(occurred_at) WHERE processed_at IS NULL;

CREATE TABLE job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type text NOT NULL, status text NOT NULL DEFAULT 'QUEUED',
  params jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb, error text,
  started_at timestamptz, finished_at timestamptz,
  created_by uuid REFERENCES app_user(id));

CREATE TABLE notification (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  kind text NOT NULL, title text NOT NULL, body text,
  entity_type text, entity_id uuid,
  severity text NOT NULL DEFAULT 'INFO',
  read_at timestamptz, dedupe_key text,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX uq_notification_dedupe ON notification(user_id, dedupe_key)
  WHERE dedupe_key IS NOT NULL;

CREATE TABLE saved_filter (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES app_user(id) ON DELETE CASCADE,
  name text NOT NULL, entity_type text NOT NULL,
  definition jsonb NOT NULL, is_pinned boolean NOT NULL DEFAULT false);

CREATE TABLE report_definition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL, source text NOT NULL,       -- зарегистрированный датасет
  columns jsonb NOT NULL, filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  grouping jsonb, sorting jsonb, chart jsonb,
  is_system boolean NOT NULL DEFAULT false);

CREATE TABLE report_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid REFERENCES report_definition(id) ON DELETE CASCADE,
  params jsonb, format text CHECK (format IN ('CSV','XLSX','PDF','JSON')),
  file_id uuid REFERENCES file_object(id) ON DELETE SET NULL,
  row_count integer, status text NOT NULL DEFAULT 'QUEUED',
  created_at timestamptz NOT NULL DEFAULT now());
```

Интеграционные заглушки (`integration_source`, `import_job`, `discovery_record`, `reconciliation_diff`) создаются в Phase 1 пустыми — чтобы поля происхождения в `ci` имели адресата и чтобы не менять схему при появлении первой интеграции.

---

## 18. Диаграммы (хранение схем)

```sql
CREATE TABLE diagram (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL, diagram_type text NOT NULL DEFAULT 'NETWORK',  -- NETWORK | POWER | LOGICAL | FLOORPLAN
  scope jsonb,                        -- автонаполнение: фильтр объектов
  location_id uuid REFERENCES location(id) ON DELETE SET NULL,
  project_id uuid REFERENCES project(id) ON DELETE SET NULL,
  viewport jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_auto_layout boolean NOT NULL DEFAULT false);

CREATE TABLE diagram_node (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  diagram_id uuid NOT NULL REFERENCES diagram(id) ON DELETE CASCADE,
  ci_id uuid REFERENCES ci(id) ON DELETE CASCADE,       -- NULL для аннотаций/групп
  node_kind text NOT NULL DEFAULT 'CI',                 -- CI | GROUP | NOTE | CLOUD
  parent_node_id uuid REFERENCES diagram_node(id) ON DELETE SET NULL,
  x numeric(10,2) NOT NULL, y numeric(10,2) NOT NULL,
  width numeric(10,2), height numeric(10,2),
  label text, style jsonb NOT NULL DEFAULT '{}'::jsonb,
  collapsed boolean NOT NULL DEFAULT false,
  UNIQUE (diagram_id, ci_id));

CREATE TABLE diagram_edge (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  diagram_id uuid NOT NULL REFERENCES diagram(id) ON DELETE CASCADE,
  connection_id uuid REFERENCES connection(id) ON DELETE CASCADE,   -- реальный кабель
  power_link_id uuid REFERENCES power_link(id) ON DELETE CASCADE,   -- либо ребро питания
  relation_id uuid REFERENCES ci_relation(id) ON DELETE CASCADE,    -- либо логическая связь
  source_node_id uuid NOT NULL REFERENCES diagram_node(id) ON DELETE CASCADE,
  target_node_id uuid NOT NULL REFERENCES diagram_node(id) ON DELETE CASCADE,
  waypoints jsonb NOT NULL DEFAULT '[]'::jsonb,
  style jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT ck_edge_backing CHECK (
    num_nonnulls(connection_id, power_link_id, relation_id) <= 1));
```

Ключевое свойство: в таблицах схемы хранится **только раскладка**. Свойства объектов и связей берутся из доменных таблиц при отрисовке, поэтому схема не может «устареть».

---

## 19. Стратегия миграций и данных

1. **Alembic с первого коммита.** `alembic upgrade head` — единственный способ создать схему; `create_all` не используется.
2. **Порядок в Phase 1:** расширения → перечисления → directory → ci → location → cmdb → служебные. Каждая последующая фаза добавляет свои таблицы отдельными ревизиями.
3. **Обратимость:** каждая миграция имеет `downgrade`; для деструктивных шагов — экспорт затрагиваемых данных в `job.result` перед изменением.
4. **Справочные данные (seed):** роли, типы документов, каталог производителей/моделей (минимальный), базовые SLA, системные отчёты — идемпотентные seed-скрипты.
5. **Демо-данные:** отдельная команда `itms seed --demo` создаёт правдоподобный пример (серверная, 2 стойки, 12 устройств, электрика, сервисы, проект «Увеличение мощности»), чтобы систему можно было оценить сразу после запуска.
6. **Тесты миграций:** прогон `upgrade head` + `downgrade base` на чистой БД в CI.

---

## 20. Сводка ключевых ограничений целостности

| Инвариант | Механизм |
|---|---|
| Уникальный код CI | Частичный уникальный индекс `WHERE deleted_at IS NULL` |
| Оборудование не перекрывается по U | `EXCLUDE USING gist` по `(rack_id, u_range)` на каждый фасад |
| Оборудование в границах стойки | Триггер с обращением к `rack.u_height` |
| Один активный кабель на порт | Частичные уникальные индексы по обеим сторонам `connection` |
| Кабель соединяет разные порты | `CHECK (a <> b)` |
| Уникальность IP в VRF | Частичный уникальный индекс |
| IP принадлежит подсети | Триггер/доменная проверка `address << prefix.cidr` |
| Питание без циклов | Доменная проверка рекурсивным CTE при вставке `power_link` |
| Зависимости CI без циклов | Доменная проверка рекурсивным CTE |
| Зависимости задач без циклов | Доменная проверка + запрет self-reference |
| Дерево локаций без циклов | Триггер пересчёта `path` + проверка префикса |
| Один `rack_mount` на объект | `UNIQUE (ci_id)` |
| Неизменяемость аудита | Отзыв прав `UPDATE/DELETE` у роли приложения |
