"""One poll cycle. Offline mode records health and does not open a socket."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote, urlsplit

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.adapters.http_client import FetchOutcome, conditional_headers, safe_get
from app.adapters.live_http import TransportError
from app.adapters.parse import (
    FeedError,
    filter_pypi,
    parse_cisa_kev,
    parse_feed,
    parse_github_release,
    parse_github_search,
    parse_hf_models,
    parse_hf_spaces,
    parse_hn_item,
)
from app.core.config import Settings
from app.core.models import Source, SourceEndpointState
from app.core.timeutil import ensure_utc, utcnow
from app.pipeline.types import SourceItemIn
from app.pipeline.urlsec import DEFAULT_ALLOWLIST, DefaultResolver
from app.services.editorial import ingest_source_item


@dataclass
class CollectReport:
    polled: int = 0
    offline: int = 0
    skipped: int = 0
    ingested: int = 0
    duplicates: int = 0
    errors: int = 0
    blocked: int = 0
    requests: int = 0
    urls: list[str] = field(default_factory=list)


def _due(source: Source, now: datetime, force: bool) -> bool:
    if force or source.last_run_at is None:
        return True
    return ensure_utc(now) >= ensure_utc(source.last_run_at) + timedelta(minutes=max(1, source.poll_interval_minutes))


ITEM_CAP = 25
_HN_COLLECTIONS = {"topstories", "newstories", "showstories"}


def _cap(source: Source) -> int:
    return max(1, int((source.policy_json or {}).get("requests_per_poll_cap") or 5))


def _empty_reason(source: Source) -> str:
    policy = source.policy_json or {}
    if source.adapter == "github_releases" and not [repo for repo in (policy.get("watched_repos") or []) if repo]:
        return "watched_repos is empty"
    if source.id == "pypi_updates" and not [name for name in (policy.get("watched_projects") or []) if name]:
        return "watched_projects is empty"
    return ""


def source_urls(source: Source) -> list[str]:
    policy = source.policy_json or {}
    adapter = source.adapter
    limit = _cap(source)
    if adapter == "github_rest_search":
        queries = [str(query) for query in (policy.get("queries") or []) if str(query).strip()]
        if not queries:
            queries = ["topic:self-hosted archived:false"]
        cursor = int(policy.get("query_cursor") or 0) % len(queries)
        ordered = queries[cursor:] + queries[:cursor]
        chosen = ordered[: min(len(ordered), limit)]
        return [f"https://api.github.com/search/repositories?q={quote(query)}&sort=updated&per_page=5" for query in chosen]
    if adapter == "github_releases":
        repos = [str(repo) for repo in (policy.get("watched_repos") or []) if repo]
        paired: list[str] = []
        for repo in repos:
            pair = [
                f"https://api.github.com/repos/{repo}",
                f"https://api.github.com/repos/{repo}/releases?per_page=3",
            ]
            if len(paired) + len(pair) > limit:
                break
            paired.extend(pair)
        return paired
    if adapter == "hf_hub":
        kinds = [str(kind) for kind in (policy.get("types") or ["models"])]
        urls = []
        if "models" in kinds:
            urls.append("https://huggingface.co/api/models?sort=createdAt&direction=-1&limit=5&full=false")
        if "spaces" in kinds:
            urls.append("https://huggingface.co/api/spaces?limit=5")
        return urls[:limit]
    if adapter == "hackernews_firebase":
        names = [str(name) for name in (policy.get("collections") or ["topstories"]) if str(name) in _HN_COLLECTIONS]
        if not names:
            names = ["topstories"]
        return [f"https://hacker-news.firebaseio.com/v0/{name}.json" for name in names][:limit]
    if adapter == "cisa_kev_json":
        url = str(policy.get("feed_url") or source.base_url or "")
        return [url] if url.startswith("https://") else []
    if adapter == "rss":
        feeds = list(policy.get("feeds") or [])
        if policy.get("feed_url"):
            feeds.append(policy["feed_url"])
        return [str(feed) for feed in feeds if str(feed).startswith("https://")][:limit]
    return []


def _fresh(item: SourceItemIn, now: datetime) -> bool:
    if item.published_at is None:
        return True
    published = ensure_utc(item.published_at)
    moment = ensure_utc(now)
    if published > moment + timedelta(days=1):
        return False
    return True


def _parse(source: Source, url: str, body: bytes, now: datetime) -> list[SourceItemIn]:
    adapter = source.adapter
    text = body.decode("utf-8", "replace")
    if adapter == "github_rest_search":
        payload = json.loads(text)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise FeedError("invalid_payload")
        return parse_github_search(payload, now)
    if adapter == "hf_hub":
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise FeedError("invalid_payload")
        rows = payload
        if "/api/spaces" in url:
            return parse_hf_spaces(rows, now)
        return parse_hf_models(rows, now)
    if adapter == "cisa_kev_json":
        return parse_cisa_kev(json.loads(text), now)
    if adapter == "rss":
        policy = source.policy_json or {}
        parsed = parse_feed(text, source.id, mark_preprints=bool(policy.get("mark_preprints")), now=now)
        if source.id == "pypi_updates":
            return filter_pypi(parsed, list(policy.get("watched_projects") or []))
        return parsed
    if adapter == "hackernews_firebase":
        return []
    return []


def _repo_from_release_url(url: str) -> dict:
    path = url.split("?", 1)[0].rstrip("/")
    parts = [part for part in path.split("/") if part]
    if "repos" in parts:
        index = parts.index("repos")
        owner = parts[index + 1] if index + 1 < len(parts) else "unknown"
        name = parts[index + 2] if index + 2 < len(parts) else "repository"
        return {"full_name": f"{owner}/{name}", "id": f"{owner}/{name}", "html_url": f"https://github.com/{owner}/{name}"}
    return {"full_name": "repository", "id": "unknown", "html_url": "https://github.com"}


def _remember_cursor(source: Source, urls: list[str]) -> None:
    if source.adapter != "github_rest_search":
        return
    policy = dict(source.policy_json or {})
    queries = [str(query) for query in (policy.get("queries") or []) if str(query).strip()]
    used = len([url for url in urls if "/search/repositories" in url])
    if not queries or used <= 0:
        return
    policy["query_cursor"] = (int(policy.get("query_cursor") or 0) + used) % len(queries)
    source.policy_json = policy
    flag_modified(source, "policy_json")


def _mark(source: Source, now: datetime, health: str, error: str = "", *, failures: int | None = None) -> None:
    source.last_run_at = now
    source.health = health
    source.last_error = error[:500]
    if health in {"ok", "partial"}:
        source.last_success_at = now
        source.consecutive_failures = 0
        source.circuit_open = False
        source.next_retry_at = None
    elif failures is not None:
        source.consecutive_failures = failures
        if failures >= 5:
            source.circuit_open = True
            source.next_retry_at = now + timedelta(minutes=30)


def collect_once(
    session: Session,
    settings: Settings,
    *,
    transport=None,
    resolver=None,
    now: datetime | None = None,
    force: bool = False,
    render: bool = False,
    llm_mode: str = "mock",
    llm_client=None,
) -> CollectReport:
    moment = ensure_utc(now or utcnow())
    report = CollectReport()
    resolver = resolver or DefaultResolver()
    sources = session.query(Source).filter(Source.enabled.is_(True)).order_by(Source.id).all()
    for source in sources:
        if source.circuit_open and source.next_retry_at and ensure_utc(source.next_retry_at) > moment and not force:
            report.skipped += 1
            continue
        if not _due(source, moment, force):
            report.skipped += 1
            continue
        if settings.source_mode != "live":
            _mark(source, moment, "offline", "SOURCE_MODE is not live")
            report.offline += 1
            continue
        if transport is None:
            _mark(source, moment, "error", "live mode has no HTTP transport", failures=source.consecutive_failures + 1)
            report.errors += 1
            continue
        missing = _empty_reason(source)
        if missing:
            _mark(source, moment, "not_configured", missing)
            report.skipped += 1
            continue
        urls = source_urls(source)
        if not urls:
            _mark(source, moment, "not_configured", "no requests configured")
            report.skipped += 1
            continue
        before = len(report.urls)
        try:
            fetched = _fetch_all(session, source, urls, transport, resolver, settings, report, moment)
        except FeedError as exc:
            _mark(source, moment, "error", str(exc), failures=source.consecutive_failures + 1)
            report.errors += 1
            continue
        _remember_cursor(source, report.urls[before:])
        if fetched is None:
            continue
        status_name, items, primary, note = fetched
        if status_name == "not_modified":
            _mark(source, moment, "ok", "not_modified")
            report.polled += 1
            continue
        if status_name == "ok" and not items:
            _mark(source, moment, "ok", note or "no_new_items")
            report.polled += 1
            continue
        if status_name in {"rate_limited", "error", "outage", "auth_error"}:
            _mark(source, moment, status_name, str(primary or status_name), failures=source.consecutive_failures + 1)
            report.errors += 1
            continue
        if status_name == "blocked":
            _mark(source, moment, "blocked", str(primary or "ssrf"), failures=source.consecutive_failures + 1)
            report.blocked += 1
            continue
        unique: list[SourceItemIn] = []
        seen: set[str] = set()
        for candidate in items:
            if candidate.source_external_id in seen:
                continue
            seen.add(candidate.source_external_id)
            unique.append(candidate)
        items = unique
        if len(items) > ITEM_CAP:
            note = (note + f" kept {ITEM_CAP} of {len(items)}").strip()
            items = items[:ITEM_CAP]
        fresh = [item for item in items if _fresh(item, moment)]
        report.blocked += len(items) - len(fresh)
        if len(fresh) < len(items):
            note = (note + f" dropped {len(items) - len(fresh)} by clock").strip()
        kept = fresh
        for item in kept:
            if item.source_id != source.id:
                item.source_id = source.id
            result = ingest_source_item(
                session,
                item,
                render=render,
                media_dir=settings.media_dir,
                llm_mode=llm_mode,
                llm_client=llm_client,
            )
            if result.duplicate:
                report.duplicates += 1
            elif result.post_id or result.story_id:
                report.ingested += 1
        if status_name == "partial" or note:
            _mark(source, moment, "partial", note or "partial")
        else:
            _mark(source, moment, "ok", "")
        report.polled += 1
    session.commit()
    return report


_BLOCKED = {"scheme", "host", "denied_host", "forbidden_ip", "ip_literal", "not_allowlisted", "dns_failed"}
_GITHUB_HOSTS = {"api.github.com", "github.com"}
_HF_HOSTS = {"huggingface.co", "cdn-lfs.huggingface.co"}


class _Budget:
    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)


_RSS_ACCEPT = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5"


def _request_headers(session: Session, source: Source, url: str, settings: Settings) -> dict[str, str]:
    row = session.query(SourceEndpointState).filter_by(source_id=source.id, request_url=url).one_or_none()
    accept = _RSS_ACCEPT if source.adapter == "rss" else "application/json"
    headers = conditional_headers(row.etag if row else "", row.last_modified if row else "", accept=accept)
    host = (urlsplit(url).hostname or "").lower()
    if host in _GITHUB_HOSTS and settings.github_read_token:
        headers["Authorization"] = f"Bearer {settings.github_read_token}"
    elif host in _HF_HOSTS and settings.hf_read_token:
        headers["Authorization"] = f"Bearer {settings.hf_read_token}"
    return headers


def _save_endpoint(session: Session, source: Source, url: str, outcome: FetchOutcome, now: datetime) -> None:
    key = outcome.final_url or url
    if key != url:
        return
    row = session.query(SourceEndpointState).filter_by(source_id=source.id, request_url=url).one_or_none()
    if row is None:
        row = SourceEndpointState(source_id=source.id, request_url=url)
        session.add(row)
    if outcome.headers.get("etag"):
        row.etag = outcome.headers["etag"][:300]
    if outcome.headers.get("last-modified"):
        row.last_modified = outcome.headers["last-modified"][:300]
    row.last_status = int(outcome.status or 0)
    row.last_checked_at = now


def _classify(outcome: FetchOutcome) -> str:
    if not outcome.ok:
        reason = outcome.reason or "error"
        return "blocked" if reason in _BLOCKED else "error"
    if outcome.status == 304:
        return "not_modified"
    if outcome.status == 401 or (outcome.status == 403 and "retry-after" not in outcome.headers):
        return "auth_error"
    if outcome.status in {403, 429}:
        return "rate_limited"
    if outcome.status >= 500:
        return "outage"
    if outcome.status != 200:
        return "error"
    return "ok"


def _fetch_all(session, source, urls, transport, resolver, settings: Settings, report: CollectReport, now: datetime):
    primary: FetchOutcome | None = None
    items: list[SourceItemIn] = []
    notes: list[str] = []
    statuses: list[str] = []
    repo_docs: dict[str, dict] = {}
    budget = _Budget(_cap(source))
    seen_hn: set[int] = set()
    hn_slots = _hn_slots(urls, budget.cap) if source.adapter == "hackernews_firebase" else {}
    for url in urls:
        if budget.remaining <= 0:
            notes.append("budget")
            break
        headers = _request_headers(session, source, url, settings)
        try:
            outcome = safe_get(
                url,
                transport,
                resolver,
                DEFAULT_ALLOWLIST,
                headers=headers,
                max_requests=budget.remaining,
            )
        except TransportError as exc:
            notes.append(exc.reason)
            statuses.append("error")
            continue
        budget.used += outcome.requests
        report.requests += outcome.requests
        report.urls.append(url)
        _save_endpoint(session, source, url, outcome, now)
        if outcome.ok and outcome.status == 200:
            primary = outcome
        kind = _classify(outcome)
        statuses.append(kind)
        if kind != "ok":
            if kind != "not_modified":
                notes.append(kind if kind != "error" else str(outcome.status or outcome.reason))
            continue
        try:
            if source.adapter == "github_releases" and "/releases" not in url.split("?", 1)[0]:
                payload = json.loads(outcome.body.decode("utf-8"))
                key = _release_key(url)
                if isinstance(payload, dict) and payload.get("full_name") == key:
                    repo_docs[key] = payload
                continue
            if source.adapter == "github_releases":
                key = _release_key(url)
                items.extend(_release_items(url, outcome.body, repo_docs.get(key), now))
            elif source.adapter == "hackernews_firebase":
                name = url.rsplit("/", 1)[-1].removesuffix(".json")
                found, truncated = _hn_items(
                    session,
                    source,
                    outcome.body,
                    transport,
                    resolver,
                    settings,
                    report,
                    budget,
                    hn_slots.get(name, 0),
                    seen_hn,
                    now,
                )
                items.extend(found)
                if truncated:
                    notes.append("budget")
            else:
                items.extend(_parse(source, url, outcome.body, now))
        except (json.JSONDecodeError, FeedError, TransportError) as exc:
            notes.append(getattr(exc, "reason", "") or "invalid_payload")
            if statuses and statuses[-1] == "ok":
                statuses[-1] = "error"
            else:
                statuses.append("error")
    return _finish(items, notes, statuses, primary)


def _finish(items, notes: list[str], statuses: list[str], primary):
    unique_notes = list(dict.fromkeys(notes))
    success = {"ok", "not_modified"}
    if statuses and set(statuses) <= {"not_modified"} and not unique_notes:
        return "not_modified", [], primary, ""
    incomplete = [status for status in statuses if status not in success]
    if not incomplete and not unique_notes:
        if not items:
            return "ok", [], primary, "no_new_items"
        return "ok", items, primary, ""
    if items or "ok" in statuses:
        return "partial", items, primary, "; ".join(unique_notes) or ",".join(incomplete)
    if "blocked" in statuses:
        return "blocked", [], unique_notes[0] if unique_notes else "blocked", ""
    if "auth_error" in statuses:
        return "auth_error", [], unique_notes[0] if unique_notes else "auth_error", ""
    if "rate_limited" in statuses:
        return "rate_limited", [], unique_notes[0] if unique_notes else "rate_limited", ""
    if "outage" in statuses:
        return "outage", [], unique_notes[0] if unique_notes else "outage", ""
    return "error", [], unique_notes[0] if unique_notes else "error", ""


def _hn_slots(urls: list[str], cap: int) -> dict[str, int]:
    names = [url.rsplit("/", 1)[-1].removesuffix(".json") for url in urls]
    if not names:
        return {}
    pool = max(0, cap - len(names))
    base, extra = divmod(pool, len(names))
    return {name: base + (1 if index < extra else 0) for index, name in enumerate(names)}


def _release_key(url: str) -> str:
    return str(_repo_from_release_url(url)["full_name"])


def _release_items(url: str, body: bytes, repo_doc: dict | None, now: datetime) -> list[SourceItemIn]:
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, list):
        raise FeedError("invalid_payload")
    rows = payload
    repo = repo_doc or _repo_from_release_url(url)
    found: list[SourceItemIn] = []
    for row in rows:
        if isinstance(row, dict) and row.get("tag_name"):
            found.append(parse_github_release(repo, row, now))
    return found


def _hn_items(
    session: Session,
    source: Source,
    body: bytes,
    transport,
    resolver,
    settings: Settings,
    report: CollectReport,
    budget: _Budget,
    slots: int,
    seen: set[int],
    now: datetime,
) -> tuple[list[SourceItemIn], bool]:
    try:
        ids = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return [], False
    if not isinstance(ids, list):
        return [], False
    found: list[SourceItemIn] = []
    truncated = False
    for raw_id in ids:
        try:
            story_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if story_id in seen:
            continue
        if len(found) >= slots or budget.remaining <= 0:
            truncated = True
            break
        seen.add(story_id)
        url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        outcome = safe_get(
            url,
            transport,
            resolver,
            DEFAULT_ALLOWLIST,
            headers=_request_headers(session, source, url, settings),
            max_requests=budget.remaining,
        )
        budget.used += outcome.requests
        report.requests += outcome.requests
        report.urls.append(url)
        _save_endpoint(session, source, url, outcome, now)
        if not outcome.ok or outcome.status != 200:
            continue
        try:
            payload = json.loads(outcome.body.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        parsed = parse_hn_item(payload, now)
        if parsed is not None:
            found.append(parsed)
    if len(ids) > len(found) and budget.remaining <= 0:
        truncated = True
    return found, truncated
