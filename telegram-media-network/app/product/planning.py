"""28-day planner. A used news cluster is not repeated. Empty slots stay empty."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.models import Channel, Episode, RankedCandidate, StoryCluster
from app.core.timeutil import ensure_utc
from app.product.programs import SERIES, _msk_slot, _quiet, ensure_series
from app.product.radar import MODEL, _primary_story

MSK = ZoneInfo("Europe/Moscow")
TTL_HOURS = {
    "event": 36,
    "cve": 14 * 24,
    "release": 21 * 24,
    "preprint": 28 * 24,
}


def propose_month(session: Session, now: datetime, *, days: int = 28) -> dict:
    ensure_series(session)
    session.flush()
    start = ensure_utc(now).astimezone(MSK).date() + timedelta(days=1)
    created = 0
    skipped: list[dict] = []
    conflicts: list[str] = []
    used: set[int] = _already_used(session)
    for offset in range(days):
        day = start + timedelta(days=offset)
        for spec in SERIES:
            if spec["period"] == "weekly" and day.weekday() != 0:
                continue
            for channel_id in spec["allowed_channels"]:
                channel = session.get(Channel, channel_id)
                if channel is None:
                    skipped.append({"series": spec["id"], "channel": channel_id, "reason": "no_channel"})
                    continue
                cap = max(1, int(channel.daily_cap or 1))
                placed_today = 0
                for slot in channel.schedule_json or []:
                    if placed_today >= cap:
                        skipped.append({"series": spec["id"], "channel": channel_id, "reason": "daily_cap", "day": day.isoformat()})
                        break
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
                        if occupied.locked:
                            used.update(int(item) for item in (occupied.item_refs or []) if str(item).isdigit())
                            continue
                        conflicts.append(f"{channel_id} {when.isoformat()} занят выпуском {occupied.id}")
                        continue
                    picks = _fresh_picks(session, channel_id, spec["max_items"], used, now, when)
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
                    session.add(
                        Episode(
                            series_id=spec["id"],
                            channel_id=channel_id,
                            slot_utc=when,
                            status="proposed",
                            item_refs=picks,
                            reason="dry-run proposal",
                            version=1,
                            origin="propose",
                            format_id=spec["style"],
                            locked=False,
                        )
                    )
                    used.update(picks)
                    created += 1
                    placed_today += 1
    session.commit()
    return {"created": created, "skipped": skipped, "conflicts": conflicts, "published": 0, "horizon_days": days}


def lock_episode(session: Session, episode: Episode, actor: str) -> Episode:
    del actor
    episode.locked = True
    episode.version += 1
    session.commit()
    return episode


def _already_used(session: Session) -> set[int]:
    used: set[int] = set()
    for episode in session.query(Episode).filter(Episode.status != "cancelled"):
        for item in episode.item_refs or []:
            try:
                used.add(int(item))
            except (TypeError, ValueError):
                continue
    return used


def _fresh_picks(session: Session, channel_id: str, limit: int, used: set[int], now: datetime, slot: datetime) -> list[int]:
    rows = (
        session.query(RankedCandidate)
        .join(StoryCluster, StoryCluster.id == RankedCandidate.cluster_id)
        .filter(
            RankedCandidate.channel_id == channel_id,
            RankedCandidate.model_version == MODEL,
            StoryCluster.primary_channel_id == channel_id,
            StoryCluster.list_name != "rejected",
            StoryCluster.status != "merged",
        )
        .order_by(RankedCandidate.rank_score.desc(), RankedCandidate.id)
        .all()
    )
    chosen: list[int] = []
    for row in rows:
        if row.cluster_id in used or row.cluster_id in chosen:
            continue
        cluster = session.get(StoryCluster, row.cluster_id)
        if cluster is None or cluster.locked:
            continue
        if not _within_ttl(session, cluster, slot):
            continue
        chosen.append(row.cluster_id)
        if len(chosen) >= limit:
            break
    return chosen


def _within_ttl(session: Session, cluster: StoryCluster, slot: datetime) -> bool:
    story = _primary_story(session, cluster)
    anchor = story.published_utc if story is not None and story.published_utc is not None else cluster.event_at or cluster.first_seen
    hours = (ensure_utc(slot) - ensure_utc(anchor)).total_seconds() / 3600
    limit = TTL_HOURS.get(cluster.event_type or cluster.kind, TTL_HOURS["event"])
    if cluster.kind == "cve":
        limit = TTL_HOURS["cve"]
    if cluster.kind == "release":
        limit = TTL_HOURS["release"]
    if story is not None and story.is_preprint:
        limit = TTL_HOURS["preprint"]
    return hours <= limit
