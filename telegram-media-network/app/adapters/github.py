from __future__ import annotations

from datetime import datetime

from app.adapters.base import DiscoverResult, SourceHealth
from app.adapters.parse import parse_github_release, parse_github_search
from app.pipeline.types import SourceItemIn


class GitHubSearchAdapter:
    source_id = "github_search"

    def __init__(self, fixture: dict | None = None, request_cap: int = 12) -> None:
        self.fixture = fixture
        self.request_cap = request_cap
        self.requests_made = 0

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        if self.fixture is None:
            return DiscoverResult(health=SourceHealth("skipped", "offline fixture missing"))
        self.requests_made = min(1, self.request_cap)
        items = parse_github_search(self.fixture)[:limit]
        return DiscoverResult(items, SourceHealth("ok", requests_made=self.requests_made))

    def validate_source(self) -> SourceHealth:
        return SourceHealth("ok" if self.fixture is not None else "offline", "fixture")


class GitHubReleasesAdapter:
    source_id = "github_releases"

    def __init__(self, repos: list[dict] | None = None, request_cap: int = 15) -> None:
        self.repos = repos or []
        self.request_cap = request_cap

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        if not self.repos:
            return DiscoverResult(health=SourceHealth("ok", "watched_repos empty"))
        items: list[SourceItemIn] = []
        requests = 0
        for row in self.repos:
            if requests >= self.request_cap or len(items) >= limit:
                break
            requests += 1
            release = row.get("release")
            if release:
                items.append(parse_github_release(row.get("repo") or row, release))
        return DiscoverResult(items, SourceHealth("ok", requests_made=requests))

    def validate_source(self) -> SourceHealth:
        return SourceHealth("ok", "watched list only")
