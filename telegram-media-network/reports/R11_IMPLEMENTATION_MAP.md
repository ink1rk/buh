# R11 Implementation Map

Telegram Media Network 4.0 — editorial factory and Pilot-Ready. Dry-run only.

## Schema

- `SCHEMA_HEAD` = `0007_r11_editorial_pilot`. `0001`–`0006` unchanged.
- Additive columns on media_assets, episodes, workflow_runs/steps, editorial_tasks/briefs/variants, lab_runs, source_items.
- New tables: `lab_daily_snapshots`, `llm_call_logs`, `source_catalog`.
- `downgrade()` raises `RuntimeError`. Forward-fix only.

## Defects

| ID | Fix |
| --- | --- |
| DEF-11-01 | Lab is a clock. Day N imports only events with `available_at <= lab_now(N)`. Daily snapshots differ. |
| DEF-11-02 | Workflow stages write artifacts or `skipped/already_satisfied` with `output_ref`. |
| DEF-11-03 | Local adapter talks to an injected client (FakeOllama in tests). Without client: `local_provider_disabled`, no socket. |
| DEF-11-04 | `_post_for` / `ensure_post_for_cluster` never takes the last post of the channel. Missing member → `needs_input` + task. |
| DEF-11-05 | Lab counts, export and purge are scoped by `lab_run_id`. |
| DEF-11-06 | Modes `historical-small` (≥40 events) and `stress-30d`. Vacancies stay honest. |
| DEF-11-07 | Growth/commerce keep unknown honest (`н/д`, provenance). |
| DEF-11-08 | Overview: на проверке vs предложенные слоты vs outbox. Radar merge by checkboxes. Russian list labels. |

## Packages

- P1 Lab 2.0 chronological clock, resume, two modes.
- P2 Source catalog + cassettes; HTTP collector coded, not activated.
- P3 LLM contract + FakeOllama; live client raises.
- P4 Executable DAG, lineage UI `/autopilot/{id}`.
- P5–P6 Desk materialise bound to cluster; JPEG MediaAsset in workflow.
- P7 Calendar statuses as CSS classes.
- P8–P9 Growth provenance and commercial funnel unchanged in honesty.
- P10 UX «Моя смена».
- P11 Ops scripts `verify_r11.py`, `r11_replay.py`, `r11_backup_restore.py`.
- P12 Pilot matrix A–E; only A boots.

## Pilot

Only `offline_replay`. `PILOT_MODE` other than that refuses boot. `ENVIRONMENT=production` still refuses boot.

PUBLISH ENABLED? NO. TELEGRAM SEND COUNT? 0. LIVE DATA? NO. REAL REVENUE? UNKNOWN. PRODUCTION READY? NO.
