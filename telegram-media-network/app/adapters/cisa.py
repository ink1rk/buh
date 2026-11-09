from __future__ import annotations

from datetime import datetime

from app.adapters.base import DiscoverResult, SourceHealth
from app.adapters.parse import parse_cisa_kev


class CisaKevAdapter:
    source_id = "cisa_kev"

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        if not self.payload:
            return DiscoverResult(health=SourceHealth("skipped", "no fixture"))
        items = parse_cisa_kev(self.payload)[:limit]
        for item in items:
            if item.cvss is not None:
                raise RuntimeError("CVSS must not be invented from KEV")
        return DiscoverResult(items, SourceHealth("ok", requests_made=1))

    def validate_source(self) -> SourceHealth:
        return SourceHealth("ok", "official json catalog")
