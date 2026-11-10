# R11 Independent Checks

Local dry-run only. No live HTTP, no Ollama socket, no Telegram.

## Runtime

- Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Redis 7 unused by this lab path, Pillow, Jinja2.
- SCHEMA_HEAD = `0007_r11_editorial_pilot`.
- Branch `cursor/tmn-r11-pilot-c7b2` from R10 `a8df9a5`.

## Automated

| Check | Result | Notes |
| --- | --- | --- |
| pytest | 192 passed | `tests/test_r8.py`, `test_r9.py`, `test_r10.py`, `test_r11.py`, `test_global.py` |
| ruff app tests | clean | |
| mypy app | clean | |
| alembic empty→head | `0007_r11_editorial_pilot` | database `tmn_r11_mig` |
| alembic 0006→head | `0007` | database `tmn_r11_from6` |
| FakeOllama | PASS | success, timeout, SSRF, injection sanitised |
| live_chat_client | raises | `reports/r11/network-gate-probes.json` |
| Telegram transport | None | send count 0 |
| production boot | RuntimeError | |
| sandbox pilot boot | RuntimeError | |

## Browser (CDP Chrome 9222, UI 8787)

Owner login. Pages: Моя смена, Радар (CVE + checkboxes), Редакция, Студия, Календарь 7/28, Автопилот lineage, Рост, Коммерция, Лаборатория, Паспорт, Качество. Viewports 375/768/1280/1600. Slot move returned **409 version_conflict**. Lab export `telegram_send=0`. Notes: `reports/screenshots/r11/browser-notes.txt`.

## Backup

`scripts/r11_backup_restore.py` dumps `tmn_r11_lab` into isolated `tmn_r11_restore` and checks `lab_daily_snapshots`, post/cluster counts, published_messages=0, and `var/media/wf-*.jpg` files on disk.

## Not run

Live GitHub/CISA/arXiv, live Ollama, Telegram sandbox, docker compose up, Proxmox, any paid API.
