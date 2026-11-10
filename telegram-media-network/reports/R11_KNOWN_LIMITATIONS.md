# R11 Known Limitations

PUBLISH ENABLED? NO.
TELEGRAM SEND COUNT? 0.
LIVE DATA? NO.
LOCAL LLM LIVE? NO.
REAL AUDIENCE? UNKNOWN.
REAL REVENUE? UNKNOWN.
PRODUCTION READY? NO.

## Blocked on purpose

- `SOURCE_MODE=live` collectors are coded (`http_collector`, allowlist, SSRF) and **not activated** (`LIVE_INGEST_ACTIVATED=False`).
- `LLM_MODE=local` without an injected `ChatClient` returns `local_provider_disabled`. `live_chat_client()` raises. No socket to Ollama.
- `PILOT_MODE` other than `offline_replay` refuses boot. Modes B–E exist as `blocked_by_policy`.
- `ENVIRONMENT=production` refuses boot.
- Telegram transport is `None`. `NEVER_PUBLISH` / `synthetic` / DEMO objects cannot send.
- `alembic downgrade` for `0007` raises `RuntimeError`.
- Compose on this VM still does not prove T17 (container TCP). Isolated Postgres restore is not a compose-volume drill (T18).

## Honest product gaps

- Growth views/subscribers remain `н/д`. No Telegram analytics API.
- Commercial prices remain `н/д`. Demo campaigns are not revenue.
- Historical-small has empty slots because the golden set is small. Stress-30d fills weekdays with synthetic rows; that is load, not demand.
- Studio pack is 48 branded 16:9 JPEGs plus three ratio samples (16:9 / 1:1 / 4:5). Workflow assets are 16:9 house templates, not licensed photography.
- Calendar `sent` never appears while dry-run is on.
- T17–T20 remain BLOCKED. R11 is offline product + Pilot-Ready code, not a live pilot.
