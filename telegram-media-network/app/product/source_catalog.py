"""Source catalog and cassette replay. HTTP collectors exist but are not activated."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.adapters.http_client import HttpResult, Transport
from app.core.config import ROOT
from app.core.models import SourceCatalogEntry

CASSETTE_DIR = ROOT / "fixtures" / "r11" / "cassettes"
CATALOG = (
    ("github_search", "GitHub Search", "api", "https://github.com", "github_search.json"),
    ("github_releases", "GitHub Releases", "api", "https://github.com", "github_releases.json"),
    ("hackernews", "Hacker News", "api", "https://news.ycombinator.com", "hackernews.json"),
    ("arxiv_science", "arXiv", "api", "https://arxiv.org", "arxiv.json"),
    ("cisa_kev", "CISA KEV", "json", "https://www.cisa.gov", "cisa_kev.json"),
    ("huggingface", "Hugging Face", "api", "https://huggingface.co", "huggingface.json"),
    ("pypi_updates", "PyPI", "api", "https://pypi.org", "pypi.json"),
    ("kubernetes", "Kubernetes", "rss", "https://kubernetes.io", "kubernetes.json"),
)
LIVE_INGEST_ACTIVATED = False


def ensure_catalog(session: Session) -> int:
    made = 0
    for source_id, title, kind, homepage, cassette in CATALOG:
        row = session.get(SourceCatalogEntry, source_id)
        if row is None:
            row = SourceCatalogEntry(id=source_id)
            session.add(row)
            made += 1
        row.title = title
        row.kind = kind
        row.homepage = homepage
        row.collector = "cassette_or_http"
        row.enabled = True
        row.live_allowed = False
        row.last_status = "cassette"
        row.cassette_path = str(CASSETTE_DIR / cassette)
        row.notes = "живой опрос не активирован"
    session.flush()
    return made


def replay_cassettes() -> list[dict]:
    rows: list[dict] = []
    for _source_id, _title, _kind, _home, cassette in CATALOG:
        path = CASSETTE_DIR / cassette
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("items") or [])
    return rows


def collect(source_id: str, *, source_mode: str = "offline", transport: Transport | None = None) -> dict:
    del transport
    if source_mode != "offline" or LIVE_INGEST_ACTIVATED:
        return {"ok": False, "status": "blocked_by_policy", "attempted": False, "source_id": source_id}
    path = CASSETTE_DIR / f"{source_id}.json"
    if not path.is_file():
        for item in CATALOG:
            if item[0] == source_id:
                path = CASSETTE_DIR / item[4]
                break
    if not path.is_file():
        return {"ok": False, "status": "cassette_missing", "attempted": False, "source_id": source_id}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "status": "cassette", "attempted": False, "source_id": source_id, "items": payload.get("items") or []}


def http_collector(url: str, transport: Transport, *, allowed_hosts: str = "127.0.0.1,localhost") -> dict:
    """Coded GET with SSRF allowlist. Not called from boot or lab."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    allowed = {item.strip().lower() for item in allowed_hosts.split(",") if item.strip()}
    if host not in allowed:
        return {"ok": False, "status": "ssrf_blocked", "attempted": False}
    result: HttpResult = transport.request("GET", url, {"Accept": "application/json"})
    return {"ok": result.status == 200, "status": result.status, "attempted": True, "body": result.body}
