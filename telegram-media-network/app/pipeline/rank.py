from __future__ import annotations

import re

from app.pipeline.types import ScoreResult, SourceItemIn

CLICKBAIT_RE = re.compile(r"шок|невероятн|вы не поверите|сенсац|!!!|бесплатно навсегда|революци", re.I)
LICENSE_CLAIM_RE = re.compile(
    r"open[- ]source|opensource|свободн\w+\s+использован|бесплатн|\bMIT\b|\bApache\b|\bGPL\b|\bBSD\b",
    re.I,
)


def score_band(total: int, hard_block: str = "") -> str:
    if hard_block:
        return "blocked"
    if total >= 80:
        return "candidate"
    if total >= 60:
        return "review"
    return "archive"


def score_item(item: SourceItemIn, channel_fit: float) -> ScoreResult:
    verifiability = 0
    if item.facts and all(fact.evidence_url.startswith("https://") and fact.evidence_excerpt for fact in item.facts):
        verifiability += 15
    if item.published_at is not None:
        verifiability += 5
    if len(item.facts) >= 2:
        verifiability += 5
    verifiability = min(25, verifiability)

    practical = 20 if item.practical and item.facts else 8
    if item.published_at is not None and item.is_new:
        novelty = 20
    elif item.published_at is not None:
        novelty = 10
    else:
        novelty = 4
    relevance = int(round(15 * max(0.0, min(1.0, channel_fit))))
    quality = 0
    if item.license_state == "explicit_open_source" or item.official_publisher:
        quality += 6
    if item.has_changelog:
        quality += 4
    quality = min(10, quality)
    audience = int(round(10 * max(0.0, min(1.0, item.audience))))
    axes = {
        "verifiability": verifiability,
        "practical_value": practical,
        "novelty": novelty,
        "channel_relevance": relevance,
        "source_quality": quality,
        "audience_significance": audience,
    }
    penalties: dict[str, int] = {}
    blob = f"{item.title}\n{item.untrusted_text}"
    if CLICKBAIT_RE.search(item.title):
        penalties["clickbait"] = 15
    if item.published_at is None:
        penalties["missing_date"] = 10
    if item.license_state != "explicit_open_source" and LICENSE_CLAIM_RE.search(blob):
        penalties["dubious_license"] = 10
    if item.press_release_only:
        penalties["press_release_only"] = 10
    if item.unsupported_high_risk:
        penalties["unsupported_high_risk_claim"] = 25
    total = max(0, min(100, sum(axes.values()) - sum(penalties.values())))
    return ScoreResult(axes=axes, penalties=penalties, total=total, band=score_band(total))
