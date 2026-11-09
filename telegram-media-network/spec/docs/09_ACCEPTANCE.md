# 09. Acceptance tests / Quality gates

Каждый test case должен иметь `id`, точные шаги, входные fixtures, ожидаемый результат, фактический PASS/FAIL и evidence (лог с redaction / скриншот / команда). Никакая задача «готово» без фактического результата.

## A. Конфигурация / модули

| ID | Test | Pass condition |
|---|---|---|
| A01 | Clean checkout + `docker compose` dev | все обязательные компоненты ready без реальных токенов |
| A02 | Load 8 channels YAML | ровно 8 уникальных slugs, TZ+caps валидны, `publish_enabled=false` |
| A03 | Upgrade DB Alembic на пустой DB | schema и indices PASS |
| A04 | API anonymous tries approve/publish | 401/403, audit, no side effects |
| A05 | Editor tries system settings | 403, role cannot self-escalate |
| A06 | Restart scheduler twice | один leader, нет двойных задач |

## B. Источники / нормализация

| ID | Test | Pass condition |
|---|---|---|
| B01 | GitHub fixture new vs updated | detected new repo vs release correctly |
| B02 | HN fixture & arXiv preprint | factual attribution, preprint marker |
| B03 | CISA KEV fixture | CVE and `dateAdded` correctly parsed, no invented CVSS |
| B04 | GitHub 403/429 | backoff obeys reset/retry-after, no tight loop |
| B05 | RSS malformed/empty/304 | no crash, source health correct |
| B06 | Temporary source outage | others continue, circuit breaker after threshold |
| B07 | Source robots/ToS blocked | source disabled, item not reused |

## C. Дедуп и редактор

| ID | Test | Pass condition |
|---|---|---|
| C01 | URL with UTM/redirect safe | same story deduplicated |
| C02 | Same repo from GitHub and HN | one story cluster, one primary channel |
| C03 | Fresh release on old repo | distinct `release:<tag>` vs root repo, policy applies |
| C04 | 2 concurrent workers | at most one publish intent and one final record |
| C05 | README contains prompt injection | LLM cannot change rules, contact bot or publish |
| C06 | Fake license and model benchmark | output blocks unsupported claim |
| C07 | arXiv preprint | labelled preprint; extraordinary claim needs review |
| C08 | low score <60 | archived not scheduled |
| C09 | score 80+ | candidate awaits approval in pilot, never auto-sent |
| C10 | high-risk CVE | second reviewer required |

## D. Медиа и Telegram

| ID | Test | Pass condition |
|---|---|---|
| D01 | Long RU heading / emoji | readable 16:9, no clipping/overflow |
| D02 | No rights for remote OG image | fallback generated locally |
| D03 | Huge/malformed image | blocked safely; process survives |
| D04 | Caption >1024 parsed chars | validator blocks/edit suggestion, no send |
| D05 | Malicious `<script>` / links | escaped; only safe links published |
| D06 | `DRY_RUN=true` publish | 0 outgoing Telegram POST (network spy proves) |
| D07 | `PUBLISH_ENABLED=false` publish | 403 or safe no-op with audit |
| D08 | channel `publish_enabled=false` | 0 outgoing send |
| D09 | Telegram mock 200 | saved message_id + timestamp + caption hash |
| D10 | Telegram mock 401/403 | channel paused, admin alerted |
| D11 | Telegram mock 429 with Retry-After | delayed retry exactly per policy |
| D12 | Timeout after request sent | NEEDS_RECONCILIATION, no blind retry |
| D13 | Crash between remote success/db commit | reconcile required, no duplicate send |

## E. Security / compliance

| ID | Test | Pass condition |
|---|---|---|
| E01 | SSRF `http://127.0.0.1`, IPv6 ULA, `169.254.169.254` | blocked before request |
| E02 | Redirect to private IP via public host | blocked on next hop |
| E03 | Source includes token-looking string | hidden from logs and generated posts |
| E04 | DB/Redis/metrics ports | no public host ports, containers non-root |
| E05 | Sponsor without legal approval | cannot approve/schedule/publish |
| E06 | No license repo | cannot claim OSS/free reuse |
| E07 | Wrong MFA/token, expired session | denied with audit and rate limiting |
| E08 | Secrets scanning and dependency audit | no critical unreviewed findings |

## F. Operations / Business

| ID | Test | Pass condition |
|---|---|---|
| F01 | Postgres encrypted backup | valid dump/checksum saved securely |
| F02 | Restore fresh DB from backup | items, posts, audit and unique constraints intact |
| F03 | Global kill switch during backlog | no further sends |
| F04 | Scheduler DST/timezone handling | correct UTC conversion for Europe/Moscow |
| F05 | Stale 2-day backlog after downtime | no uncontrolled burst publication |
| F06 | Telegram views not available | UI says unavailable/manual, never fabricated |
| F07 | 1,000 source items / 50 posts synthetic load | meets measured NFR or reports capacity failure |
| F08 | 14-day pilot report | actual sample quality stats and editorial sign-off |

## Gate release conditions

- **G1–G4**: all A/B/C/D PASS on mock, media previews attached.
- **G5**: all E + F01–F05 PASS, `pip-audit`/SBOM, documented exceptions, tested restore.
- **G6**: requires explicit permission for sandbox channel/temporary token, successful verified canary. Not automatic.
- **G7**: user approval of VM/network, bot, channel IDs, credentials, published content policy and advertising law; approval recorded outside code.

If a test cannot run due to missing external permission, label `BLOCKED` with exact missing permission; do not mark PASS. Tests written but not executed = `NOT_RUN`.
