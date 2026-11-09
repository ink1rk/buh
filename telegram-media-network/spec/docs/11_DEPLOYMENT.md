# 11. Развёртывание и ввод в эксплуатацию

## Нулевой принцип

Этот документ — **план**, а не разрешение выполнять команды. На существующих Proxmox VE и VM104/106 ничего не менять автоматически. W-PVE и W-NETWORK остаются blocked. Cursor может работать в новом локальном dev окружении на предоставленной рабочей машине; доступ к host с правами администрирования не подразумевается.

## Dev

Создать новый репозиторий под проект. Использовать test-only `.env` без реальных токенов. `docker compose -f compose.dev.yaml up --build` должен запускать mock source adapters, mock LLM, mock Telegram, PostgreSQL и Redis. `pytest` запускает unit/integration/security. Seed data из `examples/` синтетические, с hard block `NEVER_PUBLISH`.

Точный `compose.dev.yaml` разрабатывается Cursor; в этом архиве **нет рабочего Docker Compose**, поскольку приложение ещё не написано. Недопустимо подменять это обещанием «готового сервера».

## Staging после одобрения

Выделенная новая VM с private IP, от 4 vCPU/8 GB/60 GB как предварительная оценка. Docker Compose с включённым dry-run, mock credentials, постоянным volume Postgres, readonly containerFS, healthcheck, storage monitoring. Админка на loopback порту и через согласованный SSH tunnel. Тестировать только на test Telegram chat/channel, который явным образом указан и имеет разрешения.

**Сетевой профиль (без inbound WAN):**

| Client | Destination | Required |
|---|---|---|
| collector | api.github.com:443, huggingface.co:443, hacker-news.firebaseio.com:443 | yes |
| collector | rss.arxiv.org:443, www.cisa.gov:443, kubernetes.io:443, pypi.org:443, developers.cloudflare.com:443 | conditional |
| publisher | api.telegram.org:443 | yes after staging permission |
| editor | approved local LLM internal endpoint | optional, explicit approval |
| admin | VM:127.0.0.1:8787 via SSH forward | yes |
| all containers | PostgreSQL / Redis in internal Compose network | yes |
| public inbound | none | **forbidden without separate W-NETWORK approval** |

No Telegram webhook needed for channel publishing; only outbound Bot API. No polling of user chats/getUpdates by default, so cannot clash with existing Telegram bot update processing. For moderation use **web UI**, not Telegram interactive bot, until separate proposal/approval. Tokens, chat IDs, usernames placeholders until provisioned.

## Production gates

Before creating VM: `PRODUCTION_APPROVAL_REQUEST.md` and explicit owner approval. Before enabling live Telegram: verify bot admin rights `can_post_messages`, channel chat_ids, rate policies, dry-run first; then test canary to designated test channel, compare actual Telegram message/photo with preview. Repeat per channel after signed approval. No batch launch all 8 without one-by-one canary. First 14 days human moderation on every post. Kill switch is always independently testable.

## Day-2 operational responsibilities

- Daily: source health, backlog, last publish, errors, media fallback rate.
- Weekly: sample factual QA (≥25 posts), duplicate quality, broken links, false positive blockers, resource consumption.
- Monthly: restore drill, secret rotation if needed, dependency vulnerability review, re-check source ToS and official API changes, unit economics.

## Restore and rollback boundaries

Restore test only in isolated test DB. Never restore over VM104/106 or change their backups. Before deployment re-check free disk, resource headroom, backup target and network policy as read-only. If anything unavailable: mark blocked, submit change request.
