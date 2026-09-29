# ITMS — бриф для агента

Этот файл читает агент, который продолжает разработку ITMS. Код продукта лежит в каталоге `itms/` репозитория. Архитектурные документы в `docs/` — замысел Phase 0; реализация уже ушла дальше, при расхождении верить коду и миграциям.

Владелец пишет по-русски. Интерфейс системы русский. Ответы владельцу — по-русски.

## Что это

ITMS — self-hosted система учёта ИТ-инфраструктуры и работы ИТ-отдела. Одна база PostgreSQL 16. Объекты, связи, стойки, питание, документы, проекты и платформа — проекции одной модели, а не отдельные справочники.

Вторую базу, Elasticsearch, отдельный сервис «для скорости» и выдуманные артикулы в каталог не добавлять.

## GitHub

Репозиторий публичный, клонируется без токена:

- https://github.com/ink1rk/buh
- владелец: `ink1rk`
- клон: `git clone https://github.com/ink1rk/buh.git`

Запись в GitHub есть у агента Cursor, запущенного на этом репозитории. Отдельного токена, пароля и deploy key в репозитории нет, и класть их сюда нельзя. Pull request создаётся средствами среды агента, не через `gh pr create`, если среда это запрещает. `gh` можно использовать только на чтение (`gh pr view`, `gh pr list`).

`main` — старая линия установки. Рабочий код ITMS — стопка черновиков. Новую работу начинать от вершины стопки, не от `main`.

Вершина на момент этого файла:

- ветка `cursor/itms-hardware-catalog-c3c7`
- коммит `b786ce9` — серверы HP и Dell по платформам
- PR https://github.com/ink1rk/buh/pull/20
- база PR: `cursor/itms-first-login-c3c7`

Имя новой ветки: `cursor/<короткое-имя>-c3c7`, только строчные буквы. База — текущая вершина, пока её не вольют.

Стопка PR снизу вверх (каждый черновик смотрит на предыдущую ветку):

| PR | Ветка | О чём |
| --- | --- | --- |
| https://github.com/ink1rk/buh/pull/6 | `cursor/itms-architecture-c3c7` | документы `docs/` |
| https://github.com/ink1rk/buh/pull/7 | `cursor/itms-phase1-foundation-c3c7` | ядро, CMDB, документы, аудит |
| https://github.com/ink1rk/buh/pull/9 | `cursor/itms-phase2-infrastructure-c3c7` | каталог, сеть, IPAM |
| https://github.com/ink1rk/buh/pull/10 | `cursor/itms-phase3-diagrams-c3c7` | схемы как проекция модели |
| https://github.com/ink1rk/buh/pull/11 | `cursor/itms-phase4-racks-c3c7` | стойки |
| https://github.com/ink1rk/buh/pull/12 | `cursor/itms-phase5-projects-c3c7` | проекты и задачи |
| https://github.com/ink1rk/buh/pull/13 | `cursor/itms-power-model-c3c7` | расчёт питания |
| https://github.com/ink1rk/buh/pull/14 | `cursor/itms-project-transition-c3c7` | план перехода и откат |
| https://github.com/ink1rk/buh/pull/15 | `cursor/itms-power-diagram-c3c7` | однолинейная схема |
| https://github.com/ink1rk/buh/pull/16 | `cursor/itms-floorplan-c3c7` | план помещения |
| https://github.com/ink1rk/buh/pull/17 | `cursor/itms-target-architecture-c3c7` | целевая схема |
| https://github.com/ink1rk/buh/pull/18 | `cursor/itms-task-workspace-c3c7` | командный центр |
| https://github.com/ink1rk/buh/pull/19 | `cursor/itms-first-login-c3c7` | `install.sh`, смена пароля при первом входе |
| https://github.com/ink1rk/buh/pull/20 | `cursor/itms-hardware-catalog-c3c7` | каталог железа, стойка, проектный офис, платформа |

В том же репозитории есть чужие черновики (банк, почта, политика). Это не ITMS, их не трогать.

## Где код

```
itms/
  api/          FastAPI, SQLAlchemy 2 async, Alembic, домен и сервисы
  web/          React 19, TypeScript, Vite, Tailwind 4, TanStack Query
  worker/       ARQ
  deploy/       docker-compose.yml и .env.example
  appliance/    заготовка поставки
  install.sh    установка и смена пароля владельца
```

Слои API: `api → services → domain → models`. Домен не ходит в HTTP и в сессию БД.

Префикс API: `/api/v1` (`itms/api/itms/core/config.py`). Сайт проксирует `/api/` на контейнер `api`.

Миграции: `itms/api/alembic/versions/`. Голова — `0017`. Цепочка линейная, `0001` … `0017`. Новая миграция продолжает `0017`, новый тип PostgreSQL enum не заводить, если хватает строки с CHECK. При старте API само выполняет `alembic upgrade head`.

Проверки перед коммитом:

```bash
cd itms/api && ruff check .
cd itms/web && npx tsc -b --pretty false && npx eslint src --max-warnings 0
```

`ruff format` в CI не требуется. В среде агента часто нет PostgreSQL, поэтому `pytest` против живой базы может не запуститься. Это нужно прямо написать в PR.

Строки интерфейса — в `itms/web/src/i18n/ru.ts`. Тип ключей строится от русского словаря. Английский файл — запасной и неполный.

## Что уже сделано сверх старого README

README в `itms/README.md` описывает фазы 1–4 и ранние проекты. Сверху этого на вершине стопки есть:

- Каталог моделей: `itms/api/itms/domain/catalog_library.py` и `catalog_hardware.py`. Цифры — типовые значения из публичных паспортов, не замер экземпляра и не выдуманный SKU. Повторная установка библиотеки не создаёт дубликаты. Кнопка в интерфейсе: «Поставить библиотеку».
- Серверы ProLiant записаны производителем **HP**. Имя HPE при установке библиотеки переносится на HP. На момент `b786ce9`: 61 серверная модель HP и 80 Dell PowerEdge (12G–16G, башни, лезвия, MX, AMD).
- Комплектация устройства: таблица `device_part`, слоты CPU `CPU1…` и DIMM `A1/CPU1`, `B1/CPU1`, … (`itms/api/itms/domain/platform_slots.py`). Плата подменяет сокет и тип памяти шасси.
- Стойка занимает среднюю колонку, не узкую полоску: `itms/web/src/features/racks/RackEditorPage.tsx`.
- Проектный офис в боковом меню: проекты, канбан `/office/kanban`, платформа `/office/platform`, бюджет `/office/finance`, шаблоны `/office/templates`. Карточка проекта открывается на доске.
- Платформа: Kubernetes, MCP, агент OpenCode, маршруты, реестры VLAN и ВМ. VLAN и ВМ не дублируются, реестры читают существующие `/ipam/vlans` и `/virtualization`. Таблицы: `k8s_cluster`, `mcp_server`, `agent_service`, `agent_mcp`, `service_route`.
- Финансы: `finance_entry`, виды BUDGET и CASHFLOW. Отдельного права нет, используются CI_READ и CI_WRITE.
- Шаблоны документов ставятся в уже существующие виды документов. Новый enum вида документа не добавлять.
- Первый вход требует сменить пароль (`must_change_password`, миграция `0014`).

`docs/README.md` всё ещё говорит, что реализация не начата. Это устарело.

## Правила, которые легко сломать

- PostgreSQL — единственная система записи.
- Каталожные модели только реальные. Сокет, слоты DIMM и корзины брать из публичного описания платформы. Сомневаешься в цифре — модель не добавлять.
- Уникальность модели: пара производитель + имя. Повторный `POST /catalog/library` дописывает пустые поля платформы и не плодит копии.
- Маршруты FastAPI с фиксированным путём регистрировать до `/{id}`.
- Схема, стойка и план — проекции данных, не отдельные рисунки.
- Секреты не коммитить. Живые пароли только в `deploy/.env` на сервере и, при первой установке, в `/root/itms-install.txt`.
- Пароль владельца при обновлении не сбрасывать. Сброс — отдельная команда `sudo bash install.sh passwd`.
- В ответах владельцу не цитировать пароли, токены и ключи, даже если они попались в файле или журнале.

## Как устроена поставка

`sudo bash install.sh` из каталога `itms` ставит Docker, создаёт `deploy/.env`, если его нет, и поднимает compose. Повторный запуск пароль владельца не меняет.

На уже установленной машине каталог установки — родитель `deploy/`, часто `/opt/itms`. Это содержимое папки `itms` из репозитория, не корень `buh`. Compose запускается из `deploy/`. Файл `deploy/.env` при замене кода сохранять.

Обновление на Ubuntu, где контейнер `itms-api-1` уже есть:

```bash
set -euo pipefail
cd /tmp
rm -rf buh-src
git clone --depth 1 -b cursor/itms-hardware-catalog-c3c7 https://github.com/ink1rk/buh.git buh-src
DEPLOY="$(sudo docker inspect itms-api-1 --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')"
ROOT="$(dirname "$DEPLOY")"
cp -a "$DEPLOY/.env" /tmp/itms.env.bak
rsync -a --delete --exclude 'deploy/.env' /tmp/buh-src/itms/ "$ROOT/"
cp -a /tmp/itms.env.bak "$DEPLOY/.env"
cd "$DEPLOY"
sudo docker compose up -d --build
sudo docker compose ps
```

После смены каталога в интерфейсе нажать «Поставить библиотеку». Новые модели попадут в базу только так.

Стек compose: PostgreSQL 16, Redis, MinIO (`pgsty/silo`), API, worker, web (nginx). Сайт слушает `WEB_PORT` из `.env`, на известной установке это 80.

## Известные машины

Паролей здесь нет. Учётные записи Proxmox и пароль владельца ITMS в git не хранятся.

Сервер на Proxmox владельца:

- узел API: `https://95.165.65.187:8080` — это Proxmox, не сайт ITMS
- рабочая ВМ `itms`, id 105, адрес `http://172.20.20.235/`, диск установки `/opt/itms`, compose в `/opt/itms/deploy`
- на неё выкладывали сборку до каталога HP/Dell (`071b4b8`). Коммит `b786ce9` туда сам не попадал: владелец обновляет офисную машину отдельно
- тестовая ВМ `itms-check`, id 112, `172.20.20.238:8080`. Это не рабочий сервер, без просьбы её не обновлять

Офисная машина — другая установка. Её адрес в репозитории не записан. Обновляется командой выше на самой машине.

Прямого SSH с агента Cursor на эти адреса нет. Ключ гостя лежит только на узле Proxmox и в git не входит.

## Куда смотреть в коде

| Задача | Место |
| --- | --- |
| Модели каталога | `itms/api/itms/domain/catalog_hardware.py`, `catalog_library.py` |
| Установка библиотеки | `itms/api/itms/services/catalog_service.py` (`install_library`) |
| Комплектация и слоты | `itms/api/itms/services/parts_service.py`, `domain/platform_slots.py` |
| Платформа k8s/MCP/маршруты | `itms/api/itms/models/platform.py`, `services/platform_service.py`, `api/routers/platform.py` |
| Бюджет и БДДС | `itms/api/itms/services/finance_service.py` |
| Шаблоны документов | `itms/api/itms/domain/document_templates.py` |
| Стойка | `itms/web/src/features/racks/RackEditorPage.tsx` |
| Проектный офис | `itms/web/src/features/office/`, `features/platform/` |
| Меню | `itms/web/src/app/layout/Sidebar.tsx` |
| Маршруты UI | `itms/web/src/app/router.tsx` |
| Словарь | `itms/web/src/i18n/ru.ts` |

Дальше развивать продукт в той же модели: новые сущности — таблицы PostgreSQL и миграция, сервис, схема API, русский словарь, экран. Каталог пополнять реальными платформами. Обновление живой машины не сбрасывает `deploy/.env` и не меняет пароль владельца.
