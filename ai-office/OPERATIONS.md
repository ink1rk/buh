# Эксплуатация

Только VM 115. Не менять другие гости, proxy CT 101, PVE firewall, reverse proxy или DNS существующего сайта.

## Состояние и остановка

```sh
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A
sudo k3s kubectl logs -n ai-core deployment/gateway --tail=30
sudo systemctl status ai-office-proxy.service ai-office-proxy-guard.service ai-office-backup.timer
```

Для приостановки работы пользователя: `/pause`, `/stopall`; для продолжения `/resume`. Уже отправленный провайдеру запрос может тарифицироваться до завершения. Операторская остановка только бота: `sudo k3s kubectl scale deployment/gateway -n ai-core --replicas=0`; запуск — replicas=1. PostgreSQL/PVC при этом сохраняются.

## Прокси

Конфигурация `/etc/ai-office-proxy/`, службы `ai-office-proxy` и `ai-office-proxy-guard`. sing-box 1.14.3, SHA-256 релизного архива: `e2bdf179c15a3652955dc44867e33ca0965c9c9b91b34267dcc5a5d639a5feee`.

Весь внешний маршрут — SOCKS5 SOCKS5 на CT proxy, порт 1080; DNS через DoH в том же proxy. HTTP HTTP на CT proxy, порт 8080 дополнительно задан в environment/APT/k3s drop-in. TUN без direct outbound. nft table `inet ai_office_proxy_guard` сохраняет запрет внешнего eth0 egress при остановке TUN. Для внутренних соединений TUN в UFW есть только узкие правила на его собственный /30 и /126.

Не выполнять `nft flush ruleset`, `iptables -F`, `ufw disable`. Для исправления прокси перезапускать только `ai-office-proxy.service`; SSH из LAN остаётся доступен. Полный откат описан в docs/operations/PROXY_PLAN.md и автоматически не выполняется, поскольку разрешил бы прямой интернет.

## Бэкапы

```sh
sudo systemctl start ai-office-backup.service
sudo journalctl -u ai-office-backup.service -n 10 --no-pager
cat /home/aioffice/.local/state/ai-office/last-backup.txt
```

Зашифрованные файлы и SHA-256: `/home/aioffice/.local/state/ai-office/backups/`. Daily 01:10 UTC + до 5 минут jitter, Persistent=true, retention 7 дней только для файлов ai-office. Эти ежедневные копии находятся на том же диске VM. Независимая автоматическая репликация пока не настроена.

Ключ age: `/home/aioffice/.local/state/ai-office/backup-age.key`, 0600. Вторая копия на Windows: `%LOCALAPPDATA%\AI-Office-Recovery\backup-age.key`, ACL владельца; в git её нет. Локальный зашифрованный дамп — в игнорируемом `artifacts/backups` рядом с проектом.

Проверка копии в отдельном временном PostgreSQL:

```sh
cd /home/aioffice/ai-office
.venv/bin/python scripts/restore_probe.py /path/to/aioffice-20261015T214444Z.dump.age
```

Это проверка существующего контрольного дампа с ожидаемой версией схемы 2 и известным smoke artifact; при будущих миграциях ожидаемую проверку надо обновить. Скрипт **не восстанавливает поверх рабочей БД**, создаёт временный Pod с emptyDir и удаляет его после проверки. Для реальной аварии сначала разворачивать отдельную цель, проверять данные, затем согласовывать переключение. Пароль роли приложения и Kubernetes Secrets не входят в логический дамп: их восстанавливает оператор отдельно.

## Обновление и откат

Перед миграцией — новый дамп. Локальный buildah, только digest-pinned base и hashed requirements. Миграции 1, 2 и 3 повторяемы (`IF NOT EXISTS`) и применяются под PostgreSQL advisory lock. Нельзя считать это автоматической системой downgrade: удаления схемы нет.

`images.lock.json` содержит app, previous_app, cursor, postgres, python и litellm. Копии OCI — `/home/aioffice/.local/state/ai-office/images/`. При восстановлении импортировать их в `sudo k3s ctr -n k8s.io images import --platform linux/amd64 ARCHIVE` и повесить имя repo@digest через `k3s ctr images tag`, иначе `imagePullPolicy: Never` даст ErrImageNeverPull. Собственные образы не опубликованы в registry.

Манифесты на VM собирает `scripts/render_deploy.py` из `/home/aioffice/.render-env`. Этот файл в git не входит. Повторный рендер без него уберёт proxy egress. LiteLLM: ConfigMap без `database_url`, секрет только `LITELLM_MASTER_KEY`. Память пода — request 1Gi, limit 2Gi. Launcher не масштабировать вместе с gateway: у них разные ServiceAccount.

Откат gateway к предыдущему текстовому режиму: использовать сохранённый `/home/aioffice/.local/state/ai-office/gateway-before-020.yaml`. Он возвращает прежний образ и выключает LLM, сохраняя данные/дополнительную схему 2. Cursor adapter при необходимости отдельно масштабировать в 0. Proxy/guard при откате приложения сохранять.

## Ошибки доставки и расходов

Не повторять `uncertain` Telegram события или LLM-вызовы автоматически. Сначала сверить доставку/задачу и Cursor Dashboard. Метрики не содержат текста сообщений; uvicorn access log отключён. Логи фиксируют тип ошибки, без ключей и пользовательского prompt. Full user export/delete UI, внешние оповещения и мониторинг RPO/RTO ещё не внедрены.

