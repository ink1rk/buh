# R11 — Telegram Media Network 4.0, 11 ноября 2026 (Europe/Moscow)

Время прогона: 00:17 Europe/Moscow. База R10: ветка `cursor/tmn-r10-mega-c7b2`, коммит `a8df9a5`. Эта поставка: ветка `cursor/tmn-r11-pilot-c7b2`. Миграция `0007_r11_editorial_pilot`. Runtime: Python 3.12.3, FastAPI 0.162.2, SQLAlchemy 2.1.8, Pydantic 2.14.3, PostgreSQL 16. Это офлайн-редакционная фабрика восьми каналов с хронологической лабораторией. Production не заявлялся. Live-проверка не заявлялась.

## Declaration

```
PUBLISH ENABLED? NO
TELEGRAM SEND COUNT? 0
LIVE DATA? NO
SOURCE LIVE? NO
LOCAL LLM LIVE? NO
REAL AUDIENCE? UNKNOWN
REAL REVENUE? UNKNOWN
PRODUCTION READY? NO
```

- `R11 OFFLINE PRODUCT: PASS` (DEF-11-01…05, A01–A16, A22–A23, S1/S2/S3)
- `R11 PILOT-READY: code only` — режимы B–E не активированы
- T17–T20: BLOCKED

Флаги поставки не менялись: `DRY_RUN=true`, `PUBLISH_ENABLED=false`, `GLOBAL_KILL_SWITCH=true`, `SPONSORED_ENABLED=false`, `SOURCE_MODE=offline`, `LLM_MODE=mock`, `PILOT_MODE=offline_replay`. `ENVIRONMENT=production` не стартует. Транспорт Telegram — `None`.

## Defects

| ID | Status | Evidence |
| --- | --- | --- |
| DEF-11-01 | PASS | Day 1 = 3 items / 2 clusters; day 15 = 25 / 17; day 30 = 50 / 42. 30 daily snapshots. |
| DEF-11-02 | PASS | Workflow steps have `output_ref` or skip reason. Render writes `var/media/wf-*.jpg`. |
| DEF-11-03 | PASS | FakeOllama `local_attempted=true`. No client → `local_provider_disabled`. SSRF blocked. `live_chat_client()` raises. |
| DEF-11-04 | PASS | Empty cluster → `needs_input`, no last-post fallback. Bound `post.story_id` ∈ cluster members. |
| DEF-11-05 | PASS | `purge_lab` scoped by `lab_run_id`. Export filters by run. |
| DEF-11-06 | PASS | Two modes; vacancies stay `пусто: нет материала`. |
| DEF-11-07 | PASS | Growth/commerce `н/д`, provenance `demo_simulated` / unknown. |
| DEF-11-08 | PASS | «Моя смена»: на проверке / предложенные слоты / outbox. Radar checkboxes. Russian labels. |

## Acceptance A01–A26

| ID | Status | Artifact |
| --- | --- | --- |
| A01 | PASS | R8/R9/R10 suite green, SCHEMA_HEAD 0007 |
| A02 | PASS | empty→head and 0006→0007 = `0007_r11_editorial_pilot` |
| A03 | PASS | `tests/test_r11.py::test_r11_a02_chrono_no_future_leak` |
| A04 | PASS | `reports/r11/lab-daily.json` day 1 ≠ 15 ≠ 30 |
| A05 | PASS | `test_r11_a11_resume_idempotent` |
| A06 | PASS | `test_r11_a09_stress_isolated` |
| A07 | PASS | `test_r11_a07_purge_scoped` |
| A08 | PASS | lineage run with brief, variants, JPEG, slot, approval_requested |
| A09 | PASS | researched `dossier:<id>` after flush; skipped stages keep `already_satisfied` |
| A10 | PASS | `test_r11_a05_no_last_post_fallback` |
| A11 | PASS | FakeOllama claims stay unverified; injection text is data |
| A12 | PASS | CVE-2026-880001 ≠ 880099; lab-runner v1.0 ≠ v2.0; RSS reprint same cluster |
| A13 | PASS | FakeOllama success / timeout / malformed path / SSRF |
| A14 | PASS | `reports/r11/network-gate-probes.json` — no public HTTP, no Ollama socket |
| A15 | PASS | `var/media/wf-*.jpg` exist; SHA on MediaAsset; overflow blocks stage |
| A16 | PASS | calendar proposed ≠ sent; browser 409 `version_conflict` |
| A17 | PASS | existing owner/editor/viewer + CSRF tests remain green |
| A18 | PASS | shared infopovod day 1 → ai_news and ai_tools separate posts |
| A19 | PASS | growth screen: 0 measured, н/д audience, DEMO provenance |
| A20 | PASS | commerce revenue н/д; SPONSORED_ENABLED false |
| A21 | PASS | screenshots 375/768/1280/1600 under `reports/screenshots/r11/` |
| A22 | PASS | production boot RuntimeError |
| A23 | PASS | transport None, published_messages 0, lab export telegram_send 0 |
| A24 | PASS | stress-30d isolated LabRun; see Global Result checks |
| A25 | PASS | `scripts/r11_backup_restore.py` → `tmn_r11_restore` |
| A26 | PASS | this file + implementation map + screenshots + JSON exports |

## Scenarios

- **S1** GitHub release `acme/lab-runner v1.0` (day 3): cluster → dossier → brief → variants → JPEG → proposed slot → approval task. Lineage UI `/autopilot/{id}`. Delivery allowed = false.
- **S2** CVE-2026-880001 day 1 bulletin, day 5 version-scope update, same cluster key. v1.0 license confirmation on day 12 is an update, not a second release. v2.0 is a different tag.
- **S3** CVE-2026-880001 RSS reprint (`origin_mode=reprint`) does not create a second independent publisher. Unverified versions stay off delivery.

Object dumps: `reports/r11/scenarios.json`, `reports/r11/workflow-traces.json`, `reports/r11/source-provenance.json`.

## Checks

- Pytest: **192 passed**, 0 skip, 0 xfail (`scripts/verify_r11.py`).
- Ruff: app + tests clean. Mypy: 81 files, no errors.
- Browser: 15 screens × 4 widths + 48 studio cards + 3 ratio samples (16:9 / 1:1 / 4:5). Slot move **409 version_conflict**.
- Alembic: empty→head and 0006→0007 = `0007_r11_editorial_pilot`. `downgrade()` raises.
- Stress-30d (isolated `tmn_r11_stress`): 226 source items, 218 clusters, 135 posts, 30 daily snapshots, 87.2 s, RSS 110 MiB, second load idempotent, telegram_send 0. File `reports/r11/stress-30d.json`.
- Backup: dump `tmn_r11_lab` → restore `tmn_r11_restore`, 42 posts / 42 assets / 30 daily rows / published_messages 0. File `reports/r11/backup-restore.json`.
- Network probes: `reports/r11/network-gate-probes.json`.

## What this is not

Not a live ingest. Not a live local LLM. Not a Telegram sandbox. Not production. Not real revenue. Not a measured audience.
