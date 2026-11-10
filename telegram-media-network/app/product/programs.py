"""Dry-run series. A thin day stays empty instead of growing a fake post."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.models import Channel, Episode, RankedCandidate, Series, StoryCluster
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
    """Fourteen Moscow days of proposals. Nothing is marked published."""
    ensure_series(session)
    session.flush()
    start = ensure_utc(now).astimezone(MSK).date() + timedelta(days=1)
    created = 0
    skipped: list[dict] = []
    conflicts: list[str] = []
    for offset in range(14):
        day = start + timedelta(days=offset)
        for spec in SERIES:
            if spec["period"] == "weekly" and day.weekday() != 0:
                continue
            for channel_id in spec["allowed_channels"]:
                channel = session.get(Channel, channel_id)
                if channel is None:
                    skipped.append({"series": spec["id"], "channel": channel_id, "reason": "no_channel"})
                    continue
                picks = _picks(session, channel_id, spec["max_items"])
                if len(picks) < spec["min_items"]:
                    skipped.append(
                        {
                            "series": spec["id"],
                            "channel": channel_id,
                            "day": day.isoformat(),
                            "reason": "not_enough_material",
                            "have": len(picks),
                            "need": spec["min_items"],
                        }
                    )
                    continue
                for slot in channel.schedule_json or []:
                    when = _msk_slot(day, str(slot))
                    if _quiet(when, channel.quiet_start, channel.quiet_end):
                        skipped.append({"series": spec["id"], "channel": channel_id, "reason": "quiet_hours"})
                        continue
                    occupied = (
                        session.query(Episode)
                        .filter(Episode.channel_id == channel_id, Episode.slot_utc == when, Episode.status != "cancelled")
                        .one_or_none()
                    )
                    if occupied is not None:
                        conflicts.append(f"{channel_id} {when.isoformat()} занят выпуском {occupied.id}")
                        continue
                    session.add(
                        Episode(
                            series_id=spec["id"],
                            channel_id=channel_id,
                            slot_utc=when,
                            status="proposed",
                            item_refs=picks,
                            reason="dry-run proposal",
                            version=1,
                        )
                    )
                    created += 1
    session.commit()
    return {"created": created, "skipped": skipped, "conflicts": conflicts, "published": 0}


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
