# R10 — карта реализации

База: R9 на `cursor/tmn-r9-product-c7b2` / `ab28d0e`. R10 добавляет медиа-OS поверх, не переписывая publishing gate.

## Схема

- `SCHEMA_HEAD` = `0006_r10_media_os`. `0001`–`0005` не менялись.
- `alembic/versions/0006_r10_media_os.py`: только `ADD COLUMN IF NOT EXISTS` и `CREATE TABLE IF NOT EXISTS`. `downgrade()` поднимает `RuntimeError`.
- `app/core/db.py::apply_schema_extras` повторяет новые колонки, чтобы session-scoped тестовая база не расходилась с create_all.
- Новые таблицы: `publisher_identities`, `source_snapshots`, `event_relations`, `story_dossiers`, `entity_mentions`, `claim_evidence`, `editorial_briefs`, `editorial_variants`, `visual_presets`, `workflow_runs`, `workflow_steps`, `editorial_tasks`, `metric_provenance`, `commercial_offers`, `commercial_line_items`, `lab_runs`, `channel_plan_settings`, `score_revisions`.
- Расширены: `source_items`, `posts`, `story_clusters`, `ranked_candidates`, `episodes`, `channel_editorial_profiles`, `editorial_claims`, `metric_observations`, `experiment_plans`, `sales_leads`, `rate_cards`.

## Логика

| Модуль | Что сделано |
| --- | --- |
| `app/product/intelligence.py` | rank-v4, publishers vs reprints, `compute_trend` по сопоставимым снимкам, `record_score_revision` |
| `app/product/radar.py` | SourceSnapshot, origin_mode, DOI/CVE/repo:tag keys, EventRelation reprint/related |
| `app/product/dossier.py` | досье, verify_claim только independent_check + второй publisher |
| `app/product/llm_contract.py` | mock/manual/local; local disabled; sanitization |
| `app/product/editorial.py` | паспорта не затирают правки, claims source_supported/unreviewed |
| `app/product/drafts.py` | EditorialBrief/Variant, text_hash, support_level=source_supported |
| `app/product/planning.py` | ChannelPlanSettings, breaking TTL vs evergreen, задачи на пустые слоты |
| `app/media/renderer.py` | fit_headline без молчаливой обрезки, 6 purposes, RATIOS, write_studio_pack_v3 |
| `app/product/workflow.py` | 12 стадий, idempotency, pause/resume/retry, delivery_allowed=false |
| `app/product/lab.py` | 30-дневный DEMO поток, идемпотентный LabRun, purge только lab_run_id |
| `app/product/commercial.py` | create/reserve/cancel offer, actual_label следует amount |
| `app/product/growth.py` | MetricProvenance, demo_simulated/db_derived/unknown |
| `app/api/product_routes.py` | dossier, lab, autopilot, offers, claim verify |
| `app/ui/pages.py` + шаблоны | /dossier /passport /autopilot /lab /shift, формы offer/pause |

## Тесты и прогон

- `tests/test_r10.py` — A01–A21.
- R8/R9/global: SCHEMA_HEAD 0006, студия 48 `<img>`, evidence `source_supported`.
- Скриншоты: `reports/screenshots/r10/`.
- Лаборатория: `reports/lab-results.json`, `reports/R10_OFFLINE_LAB_REPORT.md`.

## Не делалось

Не включались `SOURCE_MODE=live`, `LLM_MODE=local` как живой вызов, `TELEGRAM_TRANSPORT=sandbox`, `DRY_RUN=false`, `SPONSORED_ENABLED=true`. Не запускался `docker compose up`. Не менялись Proxmox, файрвол, VPN, NAT, DNS и чужие проекты.
