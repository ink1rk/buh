# Проверки, 2026-10-16 (MSK)

Все указанные PASS основаны на фактическом выполнении. В именах дампов используется UTC.

## Выполненные проверки

| Проверка | Результат | Доказательство |
|---|---|---|
| Unit + PostgreSQL integration | PASS | `scripts/run_integration_tests.py`: Ran 42 tests, OK, 0 skipped; отдельная aioffice_test |
| Параллельный Telegram update | PASS | 8 обработчиков одного update → 1 task и 1 исходящее событие |
| ACL владельца/чата и память | PASS | Чужой user/group отклонён; нельзя завершить чужую задачу; история другого владельца не попадает в prompt |
| Напоминания/DST | PASS в тестовой БД | Отказ без зоны; неоднозначные часы требуют offset; 2 scheduler не создают дубль; pause/stopall блокируют ожидающие отправки |
| Capability артефакта | PASS | TTL, привязка к задаче, отказ отменённой задаче, повтор одинакового результата идемпотентен, изменение результата отвергнуто |
| Лимит резерва | PASS | После 40 × $0.50 следующий вызов блокируется до обращения к провайдеру; неудачный вызов автоматически не повторяется |
| Telegram Bot API | PASS | getMe ok; getWebhookInfo url пустой; polling readiness ready |
| Cursor account/catalog | PASS | Официальный GET /v1/models → 200; grok-4.7 присутствует |
| Grok на хосте | PASS | Официальный SDK с tools=[] → finished, ai-office-ok |
| Grok в Kubernetes | PASS | scripts/cursor_pod_probe.py → ai-office-ok, tools_enabled=false, run-1b3c6b9d-254a-4ee2-b199-9387cd618a5b; 7201 reported tokens |
| Фактическая стоимость Cursor | BLOCKED | get_usage: feature_unavailable для аккаунта. Оценка второго smoke $0.010686, не подтверждённое списание |
| Сохранение результата Job после TTL | PASS | task f0241b3b-1d45-4396-a807-21864ed6e992 → succeeded, artifacts=1; Job/Pod в ai-jobs уже отсутствовали |
| NetworkPolicy | PASS | gateway HTTP 200 и HTTPS через proxy 200; запрещённый PostgreSQL → CNI deny counter 0 → 1, правило REJECT |
| Прозрачный proxy без env | PASS | curl --noproxy '*' без всех proxy env → тот же внешний IP, что у явного HTTP proxy |
| Прямой выход eth0 | PASS | Принудительный --interface eth0 → ошибка; nft deny counter увеличился |
| TUN остановлен | PASS | Без proxy env запрос отклонён, прямого fallback нет; явный HTTP proxy работает; TUN снова запущен, gateway ready |
| Бэкап/восстановление | PASS | Отдельный PostgreSQL, рабочий дамп после копирования на компьютер и обратно; schema version=2, smoke artifact=1 |
| Kustomize | PASS | `kubectl apply --dry-run=server -k deploy/k3s`: все namespace, квоты, сервисы, workloads и NetworkPolicy приняты сервером |
| PVE/прежние гости/сайт | PASS по доступности | PVE 9.2.2; 100/101/102/103/115 running; существующий HTTPS=200. Нагрузочное сравнение не выполнялось |

Рабочий дамп: `aioffice-20261015T214444Z.dump.age`.
SHA-256: `ef56b48f0825651e251dfed54d07de1646ab04d972a3f66d577850b942e7781d`.
Проверка восстановления: `RESTORE PASS: separate PostgreSQL instance; verified=2:1`.

## Исходная матрица приёмки

| ID | Статус | Что осталось сверх пройденных локальных проверок |
|---|---|---|
| T01 | BLOCKED | Живое повторное событие Telegram и доставка полного ответа; дедупликация БД проходит |
| T02 | BLOCKED | Полный сценарий рестарта с напоминаниями/ожидаемыми approvals; обновление gateway и сохранность БД проверены |
| T03 | BLOCKED | Календарь не выбран/не подключён |
| T04 | BLOCKED | Нет календарного адаптера; негативные policy-проверки проходят, внешние записи выключены |
| T05 | BLOCKED | Нет approval UI и операции записи |
| T06 | BLOCKED | Нет совместимого fallback; живой LLM 429 не тестировался |
| T07 | BLOCKED | Нет tools/Kubernetes token у рабочих контейнеров; полный атакующий сценарий исполнения ещё не поставлен |
| T08 | BLOCKED | Глобальный резерв тестируется; строгий фактический cap и task cost cancellation не подтверждены |
| T09 | BLOCKED | Нет проверки убийства настоящего работающего специалиста и восстановления checkpoints |
| T10 | BLOCKED | Агентные дискуссии ещё не реализованы; Task-tool в Cursor запрещён |
| T11 | BLOCKED | DST/backlog проходят в тестах; зона владельца и живая доставка не подтверждены |
| T12 | PASS | Логический дамп рабочей БД восстановлен в отдельном экземпляре |
| T13 | PASS | Статус прежних гостей running и сайт 200; без нагрузочного SLO |
| T14 | BLOCKED | Concurrent DB tests проходят; живой rollout двух worker replicas и внешние операции не проверены |
| T15 | BLOCKED | Изоляция ключей и tools=[] настроены; полный end-to-end prompt injection сценарий не выполнялся |

G1 BLOCKED полным VM backup/restore и постоянной независимой копией. G2 BLOCKED календарём/approvals и живыми сценариями. G3 BLOCKED LiteLLM/virtual keys, точным биллингом и fallback. G4 BLOCKED trusted launcher, реальным исследованием и failure/recovery. Готовность 100% не заявляется.

