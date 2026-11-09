from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.pipeline.types import Fact, SourceItemIn

NOW = datetime(2026, 11, 10, 6, 10, tzinfo=timezone.utc)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fact(fid: str, statement: str, url: str, excerpt: str | None = None) -> Fact:
    return Fact(id=fid, statement=statement, evidence_url=url, evidence_excerpt=(excerpt or statement)[:160])


def item(**overrides) -> SourceItemIn:
    url = overrides.pop("source_url", "https://github.com/acme/widget")
    base = dict(
        source_id="github_search",
        source_external_id="github:1001",
        source_url=url,
        canonical_url=url,
        title="Acme Widget adds a local task runner",
        discovered_at=NOW,
        published_at=NOW,
        raw_sha256=sha(url + overrides.get("source_external_id", "github:1001")),
        license_state="explicit_open_source",
        facts=[
            fact("f1", "Acme Widget запускает локальные задачи из командной строки.", url, "local task runner"),
            fact("f2", "В описании репозитория указан сценарий для ежедневных операций.", url, "daily operations"),
        ],
        content_kind="repo",
        license_spdx="Apache-2.0",
        is_preprint=False,
        topics=[],
        untrusted_text="A local task runner for daily operations.",
        official_publisher=False,
        has_changelog=True,
        practical=True,
        is_new=True,
        audience=0.8,
        repo_id="1001",
    )
    base.update(overrides)
    if "raw_sha256" not in overrides:
        base["raw_sha256"] = sha(base["source_url"] + base["source_external_id"])
    return SourceItemIn(**base)
