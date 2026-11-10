"""Dry-run series. A thin day stays empty instead of growing a fake post."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.models import Episode, RankedCandidate, Series, StoryCluster
from app.core.timeutil import ensure_utc
from app.product.radar import MODEL

MSK = ZoneInfo("Europe/Moscow")


class SeriesSpec(TypedDict):
    id: str
    title: str
    allowed_channels: list[str]
    period: str
    min_items: int
    max_items: int
    style: str
    rules_json: dict[str, bool]


SERIES: tuple[SeriesSpec, ...] = (
    {
        "id": "ai_daily",
        "title": "Новости AI за день",
        "allowed_channels": ["ai_news"],
        "period": "daily",
        "min_items": 3,
        "max_items": 5,
        "style": "digest",
        "rules_json": {"second_reviewer": False},
    },
    {
        "id": "tool_day",
        "title": "Инструмент дня",
        "allowed_channels": ["ai_tools", "github", "dev"],
        "period": "daily",
        "min_items": 1,
        "max_items": 1,
        "style": "tool",
        "rules_json": {"license_unconfirmed": True},
    },
    {
        "id": "cve_review",
        "title": "Разбор CVE",
        "allowed_channels": ["cyber"],
        "period": "daily",
        "min_items": 1,
        "max_items": 1,
        "style": "security",
        "rules_json": {"second_reviewer": True},
    },
    {
        "id": "selfhosted_week",
        "title": "Self-hosted недели",
        "allowed_channels": ["homelab", "infra"],
        "period": "weekly",
        "min_items": 5,
        "max_items": 5,
        "style": "digest",
        "rules_json": {"second_reviewer": False},
    },
    {
        "id": "science_week",
        "title": "Научная неделя",
        "allowed_channels": ["future"],
        "period": "weekly",
        "min_items": 3,
        "max_items": 5,
        "style": "digest",
        "rules_json": {"preprint": True},
    },
)


def ensure_series(session: Session) -> None:
    for spec in SERIES:
        row = session.get(Series, spec["id"])
        if row is None:
            session.add(Series(timezone="Europe/Moscow", enabled=True, **spec))
        else:
            row.title = spec["title"]
            row.allowed_channels = spec["allowed_channels"]
            row.min_items = spec["min_items"]
            row.max_items = spec["max_items"]
            row.rules_json = spec["rules_json"]


def propose_fortnight(session: Session, now: datetime) -> dict:
    """Compatibility wrapper. The live planner fills 28 Moscow days without reusing a news cluster."""
    from app.product.planning import propose_month

    return propose_month(session, now, days=28)


def move_episode(session: Session, episode: Episode, slot_utc: datetime, expected_version: int) -> Episode:
    if episode.version != expected_version:
        raise ValueError("version_conflict")
    when = ensure_utc(slot_utc)
    other = (
        session.query(Episode)
        .filter(
            Episode.channel_id == episode.channel_id,
            Episode.slot_utc == when,
            Episode.id != episode.id,
            Episode.status != "cancelled",
        )
        .one_or_none()
    )
    if other is not None:
        raise ValueError("slot_conflict")
    episode.slot_utc = when
    episode.version += 1
    episode.status = "proposed"
    session.commit()
    return episode


def _picks(session: Session, channel_id: str, limit: int) -> list[int]:
    rows = (
        session.query(RankedCandidate)
        .join(StoryCluster, StoryCluster.id == RankedCandidate.cluster_id)
        .filter(
            RankedCandidate.channel_id == channel_id,
            RankedCandidate.model_version == MODEL,
            StoryCluster.primary_channel_id == channel_id,
            StoryCluster.list_name != "rejected",
        )
        .order_by(RankedCandidate.rank_score.desc())
        .limit(limit)
        .all()
    )
    return [row.cluster_id for row in rows]


def _msk_slot(day, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=MSK)
    return local.astimezone(timezone.utc)


def _quiet(moment: datetime, start: str, end: str) -> bool:
    local = moment.astimezone(MSK)
    current = local.hour * 60 + local.minute
    begin_h, begin_m = (int(part) for part in start.split(":"))
    end_h, end_m = (int(part) for part in end.split(":"))
    begin = begin_h * 60 + begin_m
    finish = end_h * 60 + end_m
    if begin <= finish:
        return begin <= current < finish
    return current >= begin or current < finish
