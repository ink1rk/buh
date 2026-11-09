# 06. Планировщик, эксплуатация, мониторинг, восстановление

## 6.1 Регламент каналов

Конфиг `configs/channels.yaml` задаёт `timezone=Europe/Moscow`, `slots`, `daily_cap=2` стартовый, `min_gap_minutes`, `publish_enabled=false`. Процесс:

1. Poll адаптеров — независимый, со случайным небольшим джиттером и backoff.
2. Раз в 10 минут scheduler выбирает `APPROVED` кандидатов, учитывает свежесть, приоритет, channel quiet hours, spread между каналами.
3. Slot выбирает 1 лучший material, резервной пост на каждый слот не обязателен.
4. `PUBLISH_ENABLED` global && channel `publish_enabled` && approved current version && legal gate && dedup && `not paused`.
5. `publisher` отправляет в Telegram только после transactional claim; логирует request fingerprint **без bot token** и response metadata.
6. Неопределённый результат → `NEEDS_RECONCILIATION` без автоматической повторной отправки.

Предлагаемые интервалы MSK: AI-news 09:10/18:10, AI-tools 10:10/19:10, GitHub 11:10/20:10, Cyber 08:40/17:40, Infra 09:40/18:40, HomeLab 12:10/21:10, Dev 10:40/19:40, Future 13:10/20:40. Это **предположения** для аудитории РФ; редактируются в UI. Quiet hours 22:00–08:00; срочные security-посты — отдельно после ручной проверки и owner override.

## 6.2 Пауза и аварийное управление

- `pause_channel` — отменяет новые scheduling leases, не удаляет очередь и старые публикации;
- `global_kill_switch=true` — всем исходящим Telegram-запросам отказ, включая ручной publish;
- `staging_mode` и `dry_run` — не менять через UI без OWNER и audit;
- `source circuit breaker` при ≥5 ошибках подряд, экспоненциальная пауза и предупреждение;
- При сбое inference не подменять генерацию «вымышленной» новостью — отправить на manual drafting.

## 6.3 Надёжность и ретраи

- Транзиентный 5xx или 429 с явным подтверждением неприёма запроса → retry с jitter, honoring `Retry-After` и отслеживанием lease; max 4 attempts и DLQ. Если подтверждения неприёма нет, рассматривается как ambiguous.
- 401/403 Bot API → немедленно pause channel и alert (проблема token/permission), без циклических повторов.
- Media rendition fail → fallback image; валидатор не разрешает текст без источника.
- Повтор scheduler tick и worker crash — не вызывают двойную публикацию по инвариантам таблиц.

## 6.4 Метрики/алерты

| Metric | Контроль |
|---|---|
| `source_poll_success_total{source}` | уровень доступности источника |
| `source_items_new_total{source}` | свежий входящий поток |
| `stories_deduped_total{strategy}` | процент дублей |
| `llm_validation_fail_total` | качество structured output |
| `fact_validation_fail_total` | недоказанные факты |
| `posts_pending_review_age_seconds` | backlog модерации |
| `media_render_seconds` | скорость генерации карточек |
| `publish_attempt_total{channel,status}` | успешность публикации |
| `publish_ambiguous_total` | неопределённый исход, всегда alert |
| `telegram_429_total` | rate limiting |
| `last_successful_publish_timestamp{channel}` | простои |
| `db_backup_age_hours` / `restore_test_age_days` | надёжность резервирования |

Уведомления: каждая `ambiguous`, 401/403, нарушение data integrity, failed backup, source outage >12 часов, отсутствие любого кандидата >48 часов (не публиковать искусственно). Не отправлять 100 одинаковых алертов; aggregations/cooldown. Место назначения — отдельный согласованный служебный Telegram-чат или локальная панель, не существующий бот без разрешения.

## 6.5 Логи и хранение

- JSON per-event: UTC ISO8601, level, component, trace_id, entity_id, action, outcome, duration_ms, redacted error code.
- Raw source snippets: 30 дней; drafts/posts/публикации — 24 месяца; operations logs 30–90 дней; security audit events ≥180 дней; media assets 180 дней, published references дольше при надобности. Конкретные сроки согласовать с юристом и доступным диском.
- Никаких secret token, Authorization headers, cookie, полного пользовательского профиля и personal IP в application logs; scrub redactor в error report.
- Metrics при нагрузке batch export, без доступа с публичного интернета.

## 6.6 Backup и restore

После approval: ежедневный PostgreSQL `pg_dump` (с шифрованием, атомарным созданием/переименованием, checksum, retention 7 daily + 4 weekly + 3 monthly), конфиги/ключи через защищённое хранилище отдельно; media по мере необходимости объектное backup. **Не полагаться только на snapshot VM**. Хранить хотя бы одну копию вне основного SSD/гипервизора после отдельного согласования. Test restore в isolated test instance не реже ежемесячно, с проверкой `COUNT`, referential integrity, ссылки на media, dry-run, `published_messages` consistency. Цели RPO ≤24h, RTO ≤4h имеют смысл только после успешного restore drill.

**Важно:** существующие незавершённые backup/restore проверки VM104/VM106 не трогать; backup нового продукта разрабатывать независимо.

## 6.7 Rollback

- App rollback = redeploy предыдущего pinned image; несовместимые миграции через expand/contract, rollback script tested.
- `global_kill_switch` перед rollback; outbox pending блокируется, сохраняется.
- Не удалять `published_messages` при rollback. Сравнить успешные Telegram IDs и БД, выполнить reconciliation.
- Тест restore и rollback сначала staging; итоговый отчёт с SHA code version и database migration revision.

## 6.8 Оценка ресурсов MVP

Новая standalone VM **после разрешения**: ориентир 4 vCPU / 8 GB RAM / 60 GB, Docker Compose, retention/картинки в ограниченном размере. Для LLM — отдельный inference endpoint (выделенный лимит, worker concurrency=1), иначе возможно повышение до 16–24 GB RAM и существенное замедление на CPU. Сначала benchmark 50 типовых новостей, только потом утверждать цифры. Пропускная способность и latency NFR измеряются в test reports.
