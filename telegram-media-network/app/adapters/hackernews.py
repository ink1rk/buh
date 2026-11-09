from __future__ import annotations

from datetime import datetime

from app.adapters.base import DiscoverResult, SourceHealth
from app.adapters.parse import parse_hn_item


class HackerNewsAdapter:
    source_id = "hackernews"

    def __init__(self, items: list[dict] | None = None, request_cap: int = 35) -> None:
        self.items = items or []
        self.request_cap = request_cap

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        parsed = []
        for row in self.items[: min(limit, self.request_cap)]:
            item = parse_hn_item(row)
            if item:
                parsed.append(item)
        return DiscoverResult(parsed, SourceHealth("ok", requests_made=min(len(self.items), self.request_cap)))

    def validate_source(self) -> SourceHealth:
        return SourceHealth("ok", "firebase fixture")
