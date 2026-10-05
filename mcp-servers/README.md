# MCP-серверы AD, Exchange и 1С

Отдельный проект. К финансовому приложению в этом репозитории не подключается: каталог `mcp-servers/` можно собрать и выложить в кластер как есть.

Три stateless MCP-сервера по Streamable HTTP. Их регистрируют в уже существующем MCP-шлюзе, агенты OpenCode ходят в шлюз.

| Сервер | Как ходит в систему | Порт в compose |
| --- | --- | --- |
| `ad` | LDAPS, сервисная учётная запись | 8081 |
| `exchange` | Microsoft Graph (по умолчанию) или on-prem EWS | 8082 |
| `onec` | OData публикации 1С, опционально HTTP-сервис | 8083 |

Эндпоинты каждого пода:

- `GET /healthz` — проверка процесса, без токена
- `POST /mcp` — MCP Streamable HTTP, ответ JSON

Запись выключена, пока на поде нет `MCP_ENABLE_WRITES=true`.

## Что умеют

**AD:** поиск пользователей, групп, компьютеров и OU; карточка пользователя; состав группы. При включённой записи: снять блокировку, включить или отключить учётку, членство в обычной группе, сброс пароля по LDAPS. Пароль в ответ не возвращается. Встроенный Administrator, krbtgt и группы Domain/Enterprise/Schema Admins, Administrators, Account Operators, Backup Operators этим сервером не меняются.

**Exchange:** найти человека, папки, список писем (тема и preview), одно письмо, календарь. Текст письма только по `include_body=true` и обрезается. Отправка и создание встречи — только при записи. Ящик передаётся в каждом вызове.

**1С:** список сущностей OData, выборка, объект по GUID, `$count`. При записи: создать, изменить, провести и отменить проведение. `onec_call_http` ходит только внутрь `ONEC_HTTP_SERVICE_URL`.

Сюда не входят дамп хэшей, Kerberoasting, DCSync и прочие атакующие сценарии, скрытые правила пересылки почты и массовая выгрузка ящиков. COM к 1С из Linux-контейнера тоже нет: снаружи базы используется OData.

## Шлюз

Upstream-адреса внутри кластера:

```text
http://mcp-ad.mcp-systems.svc.cluster.local:8080/mcp
http://mcp-exchange.mcp-systems.svc.cluster.local:8080/mcp
http://mcp-onec.mcp-systems.svc.cluster.local:8080/mcp
```

Шлюз должен слать `Content-Type: application/json` и `Accept: application/json`. Если задан `MCP_AUTH_TOKEN`, на `/mcp` нужен `Authorization: Bearer <тот же токен>`. Сессии нет (`MCP_STATELESS=true`), липкие сессии не нужны. Если конкретный шлюз требует `mcp-session-id`, поставьте `MCP_STATELESS=false` и session affinity.

Пример для OpenCode, который смотрит на шлюз, а не на поды: [deploy/opencode.jsonc](deploy/opencode.jsonc). На старых сборках OpenCode тот же блок лежит прямо в `mcp`, без вложенного `servers`. Таймаут инструментов лучше поднять: каталог и 1С часто не укладываются в 5 секунд.

Когда пришлёте манифест шлюза, upstream можно вписать в его формат один в один. Черновик URL: [deploy/k8s/gateway.example.yaml](deploy/k8s/gateway.example.yaml).

## Запуск

```bash
cd mcp-servers
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v

# один сервер локально, stdio или HTTP
export AD_SERVER=dc.example.local AD_BIND_USER='EXAMPLE\svc' AD_BIND_PASSWORD=... AD_BASE_DN='DC=example,DC=local'
python -m ad
```

Образы:

```bash
docker build --build-arg SERVICE=ad -t mcp-ad:local .
docker build --build-arg SERVICE=exchange -t mcp-exchange:local .
docker build --build-arg SERVICE=onec -t mcp-onec:local .
```

В кластере поправьте адреса в ConfigMap, создайте секреты из [deploy/k8s/secrets.example.yaml](deploy/k8s/secrets.example.yaml) и примените каталог:

```bash
kubectl apply -k deploy/k8s
```

Секреты в kustomization не входят, чтобы примерные пароли не уехали в кластер вместе с манифестами.

## Переменные

Общие: `MCP_HOST`, `MCP_PORT` (8080), `MCP_PATH` (`/mcp`), `MCP_AUTH_TOKEN`, `MCP_ENABLE_WRITES`, `MCP_STATELESS`, `MCP_JSON_RESPONSE`, `MCP_TRANSPORT` (`streamable-http` или `stdio`).

**AD:** `AD_SERVER`, `AD_PORT`, `AD_USE_SSL`, `AD_STARTTLS`, `AD_TLS_VERIFY`, `AD_BIND_USER`, `AD_BIND_PASSWORD`, `AD_BASE_DN`, `AD_TIMEOUT`.

**Exchange Graph** (`EXCHANGE_MODE=graph`): `EXCHANGE_TENANT_ID`, `EXCHANGE_CLIENT_ID`, `EXCHANGE_CLIENT_SECRET`. Приложению нужны права приложения с admin consent: `User.Read.All`, `Mail.Read`, `Mail.Send`, `Calendars.ReadWrite`. Лишние права можно не выдавать: инструмент упрётся в 403.

**Exchange EWS** (`EXCHANGE_MODE=ews`): `EXCHANGE_EWS_URL`, `EXCHANGE_USERNAME`, `EXCHANGE_PASSWORD`, `EXCHANGE_AUTH` (`ntlm` или `basic`), `EXCHANGE_IMPERSONATE`, `EXCHANGE_VERIFY_TLS`, `EXCHANGE_VERSION`.

**1С:** `ONEC_BASE_URL` (публикация `.../odata/standard.odata`), `ONEC_USERNAME`, `ONEC_PASSWORD`, `ONEC_VERIFY_TLS`, необязательный `ONEC_HTTP_SERVICE_URL`. У пользователя 1С должны быть права на нужные объекты OData.

Поиск в AD ограничен базой `AD_BASE_DN`. Запросы 1С не уходят с настроенного хоста и не следуют редиректам.
