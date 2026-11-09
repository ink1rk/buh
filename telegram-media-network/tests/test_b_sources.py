from __future__ import annotations

from app.adapters.http_client import HttpResult, backoff_seconds, fetch_with_backoff, interpret_status
from app.adapters.parse import parse_cisa_kev, parse_github_release, parse_github_search, parse_hn_item
from app.adapters.policy import CircuitState, apply_robots
from app.adapters.rssfeed import RssAdapter
from app.core.models import Source, Story
from app.pipeline.dedup import identity_keys
from tests.factories import NOW, item
from tests.support import ingest

GITHUB_NEW = {
    "items": [
        {
            "id": 501,
            "full_name": "acme/widget",
            "html_url": "https://github.com/acme/widget",
            "description": "Local task runner for daily operations",
            "fork": False,
            "archived": False,
            "created_at": "2026-11-01T00:00:00Z",
            "pushed_at": "2026-11-09T00:00:00Z",
            "license": {"spdx_id": "Apache-2.0"},
            "topics": [],
        }
    ]
}
GITHUB_OLD = {
    "items": [
        {
            "id": 502,
            "full_name": "acme/old",
            "html_url": "https://github.com/acme/old",
            "description": "Older library",
            "created_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2026-11-09T00:00:00Z",
            "license": {"spdx_id": "MIT"},
            "topics": [],
        }
    ]
}


def test_b01_new_repo_versus_release():
    new = parse_github_search(GITHUB_NEW, NOW)[0]
    old = parse_github_search(GITHUB_OLD, NOW)[0]
    release = parse_github_release(
        {"id": 501, "full_name": "acme/widget", "html_url": "https://github.com/acme/widget", "license": {"spdx_id": "Apache-2.0"}},
        {"tag_name": "v1.2.0", "html_url": "https://github.com/acme/widget/releases/tag/v1.2.0", "body": "Adds a local runner", "published_at": "2026-11-09T00:00:00Z"},
        NOW,
    )
    assert new.is_new is True
    assert old.is_new is False
    assert new.content_kind == "repo"
    assert release.content_kind == "release"
    assert "github-release:501:v1.2.0" in identity_keys(release)
    assert "github:501" in identity_keys(new)


def test_b02_hn_arxiv_preprint():
    parsed = parse_hn_item(
        {"id": 42, "type": "story", "title": "A robotics preprint", "url": "https://arxiv.org/abs/2601.01234v2", "time": 1762733400},
        NOW,
    )
    assert parsed is not None
    assert parsed.is_preprint is True
    assert parsed.facts[0].statement.startswith("Hacker News")
    assert "arxiv.org" in parsed.source_url


def test_b03_cisa_does_not_invent_cvss():
    rows = parse_cisa_kev(
        {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-1000",
                    "dateAdded": "2026-11-01",
                    "vendorProject": "Example",
                    "product": "Widget",
                    "shortDescription": "A flaw in the widget parser.",
                    "requiredAction": "Apply the vendor update.",
                    "cvssScore": 9.8,
                }
            ]
        },
        NOW,
    )
    assert rows[0].cve_id == "CVE-2026-1000"
    assert rows[0].date_added == "2026-11-01"
    assert rows[0].cvss is None
    assert "9.8" not in rows[0].untrusted_text


def test_b04_github_backoff_waits_for_retry_after():
    assert backoff_seconds(429, {"Retry-After": "12"}, 1, 1_700_000_000) == 12
    assert backoff_seconds(429, {"Retry-After": "0"}, 1, 1_700_000_000) >= 1
    reset = 1_700_000_030
    assert backoff_seconds(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}, 1, 1_700_000_000) == 30
    slept = {"done": False, "delays": []}

    def fetch():
        if not slept["done"]:
            return HttpResult(429, {"Retry-After": "12"})
        return HttpResult(200, {})

    def sleeper(delay):
        slept["delays"].append(delay)
        slept["done"] = True

    result = fetch_with_backoff(fetch, sleeper, lambda: 1_700_000_000.0)
    assert slept["delays"] == [12]
    assert result.status == 200


def test_b05_rss_malformed_empty_and_not_modified():
    empty = RssAdapter("kubernetes", "   ", feed_url="https://kubernetes.io/feed.xml").discover(None, 5)
    assert empty.items == []
    assert empty.health.status == "ok"
    broken = RssAdapter("kubernetes", "<rss", feed_url="https://kubernetes.io/feed.xml").discover(None, 5)
    assert broken.health.status == "error"
    assert interpret_status(304) == "not_modified"


def test_b06_outage_opens_one_circuit_only():
    failed = CircuitState()
    healthy = CircuitState()
    for _ in range(5):
        failed.note_failure("timeout", NOW)
    healthy.note_success(NOW)
    assert failed.circuit_open is True
    assert failed.allow_request(NOW) is False
    assert healthy.allow_request(NOW) is True


def test_b07_robots_block_stops_reuse(db):
    state = CircuitState()
    robots = "User-agent: *\nDisallow: /\n"
    assert apply_robots(state, robots, "https://example.com/feed") is False
    source = db.get(Source, "github_search")
    source.robots_blocked = True
    source.enabled = False
    source.last_error = "robots_disallow"
    db.commit()
    result = ingest(db, item(source_id="github_search"))
    assert result.status == "BLOCKED_SOURCE"
    assert db.query(Story).count() == 0
