from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.pipeline.types import SourceItemIn


@dataclass
class SourceHealth:
    status: str
    detail: str = ""
    not_modified: bool = False
    requests_made: int = 0


@dataclass
class DiscoverResult:
    items: list[SourceItemIn] = field(default_factory=list)
    health: SourceHealth = field(default_factory=lambda: SourceHealth("ok"))


class SourceAdapter(Protocol):
    source_id: str

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult: ...

    def validate_source(self) -> SourceHealth: ...
