from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.timeutil import ensure_utc


@dataclass
class Fact:
    id: str
    statement: str
    evidence_url: str
    evidence_excerpt: str


@dataclass
class SourceItemIn:
    source_id: str
    source_external_id: str
    source_url: str
    title: str
    discovered_at: datetime
    published_at: datetime | None
    raw_sha256: str
    license_state: str
    facts: list[Fact]
    canonical_url: str | None = None
    content_kind: str = "news"
    language: str | None = None
    license_spdx: str | None = None
    is_preprint: bool = False
    topics: list[str] = field(default_factory=list)
    untrusted_text: str = ""
    official_publisher: bool = False
    has_changelog: bool = False
    practical: bool = True
    is_new: bool = True
    audience: float = 0.7
    repo_id: str | None = None
    release_tag: str | None = None
    cve_id: str | None = None
    date_added: str | None = None
    cvss: float | None = None
    synthetic: bool = False
    press_release_only: bool = False
    unsupported_high_risk: bool = False
    link_broken: bool = False
    archived: bool = False
    fork: bool = False
    categories: list[str] = field(default_factory=list)

    def _stamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return ensure_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")

    def contract(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_external_id": self.source_external_id,
            "source_url": self.source_url,
            "canonical_url": self.canonical_url,
            "title": self.title[:400],
            "discovered_at": self._stamp(self.discovered_at),
            "published_at": self._stamp(self.published_at),
            "raw_sha256": self.raw_sha256,
            "content_kind": self.content_kind,
            "language": self.language,
            "license_state": self.license_state,
            "license_spdx": self.license_spdx,
            "is_preprint": self.is_preprint,
            "facts": [
                {
                    "id": fact.id,
                    "statement": fact.statement[:400],
                    "evidence_url": fact.evidence_url,
                    "evidence_excerpt": fact.evidence_excerpt[:160],
                }
                for fact in self.facts
            ],
        }


@dataclass
class RouteDecision:
    primary: str
    alternatives: list[str]
    confidence: float
    reason: str


@dataclass
class ScoreResult:
    axes: dict[str, int]
    penalties: dict[str, int]
    total: int
    band: str
    rubric_version: str = "rubric-v1"


@dataclass
class DraftResult:
    blocked: bool
    reason: str
    warnings: list[str]
    draft: dict | None
    public_text: str
