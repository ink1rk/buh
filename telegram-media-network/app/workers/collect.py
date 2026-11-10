"""One poll cycle. Offline mode records health and does not open a socket."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.adapters.http_client import FetchOutcome, conditional_headers, safe_get
from app.adapters.parse import (
    FeedError,
    parse_cisa_kev,
    parse_feed,
    parse_github_search,
    parse_hf_models,
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


def source_urls(source: Source) -> list[str]:
    policy = source.policy_json or {}
    adapter = source.adapter
    if adapter == "github_rest_search":
        query = ((policy.get("queries") or ["topic:self-hosted archived:false"])[0])
        return [f"https://api.github.com/search/repositories?q={quote(query)}&sort=updated&per_page=5"]
    if adapter == "github_releases":
        repos = [str(repo) for repo in (policy.get("watched_repos") or []) if repo]
        return [f"https://api.github.com/repos/{repo}/releases?per_page=3" for repo in repos[:5]]
    if adapter == "hf_hub":
        return ["https://huggingface.co/api/models?limit=5&full=false"]
    if adapter == "hackernews_firebase":
        return ["https://hacker-news.firebaseio.com/v0/topstories.json"]
    if adapter == "cisa_kev_json":
        url = str(policy.get("feed_url") or source.base_url or "")
        return [url] if url.startswith("https://") else []
    if adapter == "rss":
        feeds = list(policy.get("feeds") or [])
        if policy.get("feed_url"):
            feeds.append(policy["feed_url"])
        return [str(feed) for feed in feeds if str(feed).startswith("https://")]
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
        return parse_hf_models(rows, now)
    if adapter == "cisa_kev_json":
        return parse_cisa_kev(json.loads(text), now)
    if adapter == "rss":
        policy = source.policy_json or {}
        return parse_feed(text, source.id, mark_preprints=bool(policy.get("mark_preprints")), now=now)
    if adapter == "hackernews_firebase":
        return []
    return []


def _mark(source: Source, now: datetime, health: str, error: str = "", *, failures: int | None = None) -> None:
    source.last_run_at = now
    source.health = health
    source.last_error = error[:500]
    if health == "ok":
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
        urls = source_urls(source)
        if not urls:
            _mark(source, moment, "ok", "no requests configured")
            report.polled += 1
            continue
        headers = conditional_headers(source.etag, source.last_modified)
        if source.adapter.startswith("github") and settings.github_read_token:
            headers["Authorization"] = f"Bearer {settings.github_read_token}"
        try:
            fetched = _fetch_all(source, urls, transport, resolver, headers, report, moment)
        except FeedError as exc:
            _mark(source, moment, "error", str(exc), failures=source.consecutive_failures + 1)
            report.errors += 1
            continue
        if fetched is None:
            continue
        status_name, items, primary = fetched
        if status_name == "not_modified":
            _mark(source, moment, "ok", "not_modified")
            report.polled += 1
            continue
        if status_name in {"rate_limited", "error", "outage", "auth_error"}:
            _mark(source, moment, status_name, primary or status_name, failures=source.consecutive_failures + 1)
            report.errors += 1
            continue
        if status_name == "blocked":
            _mark(source, moment, "blocked", primary or "ssrf", failures=source.consecutive_failures + 1)
            report.blocked += 1
            continue
        kept = [item for item in items if _fresh(item, moment)]
        report.blocked += len(items) - len(kept)
        for item in kept:
            if item.source_id != source.id:
                item.source_id = source.id
            result = ingest_source_item(session, item, render=render, media_dir=settings.media_dir)
            if result.duplicate:
                report.duplicates += 1
            elif result.post_id or result.story_id:
                report.ingested += 1
        if primary and primary.headers.get("etag"):
            source.etag = primary.headers["etag"][:300]
        if primary and primary.headers.get("last-modified"):
            source.last_modified = primary.headers["last-modified"][:300]
        _mark(source, moment, "ok")
        report.polled += 1
    session.commit()
    return report


_BLOCKED = {"scheme", "host", "denied_host", "forbidden_ip", "ip_literal", "not_allowlisted", "dns_failed"}


def _fetch_all(source, urls, transport, resolver, headers, report: CollectReport, now: datetime):
    primary: FetchOutcome | None = None
    items: list[SourceItemIn] = []
    cap = int((source.policy_json or {}).get("requests_per_poll_cap") or 5)
    for url in urls[:cap]:
        outcome = safe_get(url, transport, resolver, DEFAULT_ALLOWLIST, headers=headers)
        report.requests += outcome.requests
        report.urls.append(url)
        primary = outcome
        if not outcome.ok:
            reason = outcome.reason or "error"
            kind = "blocked" if reason in _BLOCKED else "error"
            return kind, [], reason
        if outcome.status == 304:
            return "not_modified", [], outcome
        if outcome.status == 401 or (outcome.status == 403 and "retry-after" not in outcome.headers):
            return "auth_error", [], str(outcome.status)
        if outcome.status in {403, 429}:
            return "rate_limited", [], str(outcome.status)
        if outcome.status != 200:
            return "error", [], str(outcome.status)
        if source.adapter == "hackernews_firebase":
            items.extend(_hn_items(outcome.body, transport, resolver, headers, report, cap, now))
        else:
            items.extend(_parse(source, url, outcome.body, now))
    return "ok", items, primary


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
