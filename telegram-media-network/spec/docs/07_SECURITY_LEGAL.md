# 07. Безопасность и правовые ограничения

## 7.1 Модель угроз

| Threat | Impact | Control |
|---|---|---|
| Prompt injection в README/новости | модель публикует чужие инструкции | source data escaping, schema-only output, deterministic validator, human gate |
| SSRF через URL/OG image/redirect | доступ к PVE, NAS, metadata, внутренней сети | allowlist, deny private/link-local, DNS pin/каждый redirect, sandbox egress, no secrets |
| Shell execution чужого кода | compromise VM | запрещён `git clone && execute`, не скачивать binaries |
| Утечка Telegram token | посторонняя публикация | separated secrets, no logs/commits, token rotation, minimal bot admin rights |
| Duplicate Telegram publish | spam/срыв доверия | DB outbox, leases, ambiguous outcome reconciliation, no blind retries |
| XSS/HTML injection | takeover admin UI | escaped templates, CSP, input sanitization, CSRF, secure cookies |
| Доступ к панели извне | unauthorized approval | localhost-only, SSH tunnel, MFA, RBAC, fail2ban/limiting where appropriate |
| Изображение с вредоносной нагрузкой | resource exhaustion / parser RCE | MIME/magic validation, pixel limit, stripped metadata, decoder isolation |
| License violation | блокировки/претензии | own summaries, attribution, image-rights registry, no copying without rights |
| Скрытая/незаконная реклама | юридический риск | commercial kill switch, separate approved legal state and markings |
| Подмена данных о CVE | вред пользователям | official CISA/vendor advisory, secondary review, fixed evidence trail |

## 7.2 Права доступа / секреты

- Private read-only GitHub/HF credential where necessary, Telegram publisher bot token secret only inside publisher container. Создать **нового** бота для этого продукта только после решения владельца; старых не трогать.
- Admin web: MFA, RBAC, session idle timeout, access logs без IP сверх необходимости, no public registration, approved origins, CSRF.
- Linux: non-root UID, read-only root filesystem, drop Linux caps, seccomp, no privileged, no `/var/run/docker.sock`, no host mounts, isolated Docker networks. Образы pinned SHA256, local SBOM и CVE review.
- PostgreSQL не публиковать на host / WAN. Redis require auth + private network, лучше без public ports. Безопасные Docker secrets или защищённый bind файл с mode 0600; никакого секретного значения в Compose/env.example.
- Secrets rotation playbook: pause outgoing, сменить secret, verify `getMe` на test account, проверить права, resume после owner approval. Не записывать токен в лог.

## 7.3 Безопасность исходящих запросов

Whitelist host names and content types; `httpx` safe fetching with redirect cap, `max_response_size`, network timeouts, DNS/IP protections, response decompress cap. No requests to private IP, localhost, PVE API, home network, 169.254.169.254, IPv6 ULA/link-local, CGNAT. Allowlist CDN media URLs **отдельный**, лучше вообще не загружать чужие картинки в MVP. Контейнер screenshot browser не видит database/redis/token volumes, запрещено automatic downloads и user uploads.

## 7.4 Контент и лицензии

- Общедоступный GitHub репозиторий не обязательно OSS; отсутствие LICENSE обычно оставляет все права автору: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
- Не копировать полные статьи, README, логотипы или скриншоты без отдельного основания. Краткий оригинальный пересказ с честной ссылкой, правила платформы/автора соблюдать. Не удалять attribution там, где требует лицензия.
- Не переписывать автоматически материалы сайтов, запрещающих машинную обработку/повторное использование; ToS/robots и правовую политику источника пересматривать.
- Публикация уязвимостей: без детальных инструкций эксплуатации и без выдачи недоказанного за факт; defensive/patch-oriented.
- Ограничение личных данных: не публиковать пользовательские e-mail/секреты и чужие внутренние IP/архивы, даже если они случайно найдены в открытом repo.

## 7.5 Реклама, юрисдикция и маркировка

**Коммерческие размещения отключены до проверки права на конкретный формат/площадку/дату.** Для РФ правила могут включать маркировку интернет-рекламы, идентификатор рекламы, передачу сведений через ОРД/ЕРИР и отраслевые ограничения. Статус Telegram как рекламной площадки и текущая правоприменительная практика меняются: ориентироваться на актуальные разъяснения ФАС и Роскомнадзора на дату запуска, а не на старые статьи. В 2026 году появлялись переходные разъяснения ФАС; они **не равны универсальному разрешению любой рекламы**. Нужна отдельная юридическая проверка. Справки: https://www.consultant.ru/document/cons_doc_LAW_429934/ ; https://www.consultant.ru/document/cons_doc_LAW_529901/ .

Для любой sponsored/affiliate публикации — UI-форма: advertiser, договор/основание, legal review approved, кто отвечает за маркировку, требуемая пометка/ID, фактическая дата, архив скриншота и source. Если закон запрещает размещение — блокировать scheduling. **Скрытую рекламу не формировать**. Рекомендации «партнёрка» не отменяют требований к маркировке.

## 7.6 Чек-лист security gate

- [ ] нет публичного ingress и host network changes;
- [ ] все токены test-only, секреты исключены из git и логов;
- [ ] SSRF tests: local/private/IPv6/metadata/redirect blocked;
- [ ] prompt injection tests: `ignore all previous instructions` из repo не влияет на действия;
- [ ] captcha/paywall/robots соблюдаются;
- [ ] caption escaped, XSS/CSRF/SQLi checks PASS;
- [ ] no unauthorized live Telegram HTTP;
- [ ] source image reuse имеет rights_basis, fallback test PASS;
- [ ] sponsor must require legal review;
- [ ] security incidents require second human approval;
- [ ] restore and kill switch tested;
- [ ] production approval запрошен отдельным документом.
