"""One poll cycle. Offline mode records health and does not open a socket."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote

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
from app.core.models import Source
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
        urls: list[str] = []
        for repo in repos:
            urls.append(f"https://api.github.com/repos/{repo}")
            urls.append(f"https://api.github.com/repos/{repo}/releases?per_page=3")
        return urls[:limit]
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
        return parse_github_search(json.loads(text), now)
    if adapter == "hf_hub":
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else []
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
        headers = conditional_headers(source.etag, source.last_modified)
        if source.adapter.startswith("github") and settings.github_read_token:
            headers["Authorization"] = f"Bearer {settings.github_read_token}"
        before = len(report.urls)
        try:
            fetched = _fetch_all(source, urls, transport, resolver, headers, report, moment)
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
        if isinstance(primary, FetchOutcome) and primary.headers.get("etag"):
            source.etag = primary.headers["etag"][:300]
        if isinstance(primary, FetchOutcome) and primary.headers.get("last-modified"):
            source.last_modified = primary.headers["last-modified"][:300]
        if status_name == "partial" or note:
            _mark(source, moment, "partial", note or "partial")
        else:
            _mark(source, moment, "ok", "")
        report.polled += 1
    session.commit()
    return report


_BLOCKED = {"scheme", "host", "denied_host", "forbidden_ip", "ip_literal", "not_allowlisted", "dns_failed"}


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


def _fetch_all(source, urls, transport, resolver, headers, report: CollectReport, now: datetime):
    primary: FetchOutcome | None = None
    items: list[SourceItemIn] = []
    notes: list[str] = []
    repo_doc: dict | None = None
    cap = _cap(source)
    for url in urls[:cap]:
        try:
            outcome = safe_get(url, transport, resolver, DEFAULT_ALLOWLIST, headers=headers)
        except TransportError as exc:
            if items:
                notes.append(exc.reason)
                continue
            return "error", [], exc.reason, ""
        report.requests += outcome.requests
        report.urls.append(url)
        primary = outcome
        kind = _classify(outcome)
        if kind in {"auth_error", "rate_limited", "blocked"}:
            return kind, [], outcome.reason or str(outcome.status), ""
        if kind != "ok":
            if items or repo_doc is not None:
                notes.append(kind if kind != "error" else str(outcome.status or outcome.reason))
                continue
            if kind == "not_modified":
                return "not_modified", [], outcome, ""
            return kind, [], outcome.reason or str(outcome.status), ""
        try:
            if source.adapter == "github_releases" and "/releases" not in url.split("?", 1)[0]:
                payload = json.loads(outcome.body.decode("utf-8"))
                if isinstance(payload, dict):
                    repo_doc = payload
                continue
            if source.adapter == "github_releases":
                items.extend(_release_items(url, outcome.body, repo_doc, now))
            elif source.adapter == "hackernews_firebase":
                budget = max(0, cap - report.requests)
                items.extend(_hn_items(outcome.body, transport, resolver, headers, report, budget, now))
            else:
                items.extend(_parse(source, url, outcome.body, now))
        except (json.JSONDecodeError, FeedError, TransportError) as exc:
            notes.append(getattr(exc, "reason", "") or str(exc)[:80])
    if not items and notes and repo_doc is None:
        return "error", [], notes[0], ""
    status = "partial" if notes else "ok"
    return status, items, primary, "; ".join(notes)


def _release_items(url: str, body: bytes, repo_doc: dict | None, now: datetime) -> list[SourceItemIn]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else []
    repo = repo_doc or _repo_from_release_url(url)
    found: list[SourceItemIn] = []
    for row in rows:
        if isinstance(row, dict) and row.get("tag_name"):
            found.append(parse_github_release(repo, row, now))
    return found


def _hn_items(body: bytes, transport, resolver, headers, report: CollectReport, cap: int, now: datetime) -> list[SourceItemIn]:
    try:
        ids = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(ids, list):
        return []
    found: list[SourceItemIn] = []
    for raw_id in ids[: max(0, cap - 1)]:
        url = f"https://hacker-news.firebaseio.com/v0/item/{int(raw_id)}.json"
        outcome = safe_get(url, transport, resolver, DEFAULT_ALLOWLIST, headers=headers)
        report.requests += outcome.requests
        report.urls.append(url)
        if not outcome.ok or outcome.status != 200:
            continue
        try:
            payload = json.loads(outcome.body.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        parsed = parse_hn_item(payload, now)
        if parsed is not None:
            found.append(parsed)
    return found
