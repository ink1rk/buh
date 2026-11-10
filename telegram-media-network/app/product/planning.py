"""28-day planner. A used news cluster is not repeated. Empty slots stay empty."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.models import (
    Channel,
    ChannelPlanSettings,
    EditorialTask,
    Episode,
    RankedCandidate,
    StoryCluster,
)
from app.core.timeutil import ensure_utc
from app.product.programs import SERIES, _msk_slot, _quiet, ensure_series
from app.product.radar import MODEL, _primary_story

MSK = ZoneInfo("Europe/Moscow")
TTL_HOURS = {
    "event": 36,
    "cve": 14 * 24,
    "release": 21 * 24,
    "preprint": 28 * 24,
    "evergreen": 90 * 24,
}


def ensure_plan_settings(session: Session) -> None:
    for channel in session.query(Channel).all():
        row = session.get(ChannelPlanSettings, channel.id)
        if row is None:
            session.add(
                ChannelPlanSettings(
                    channel_id=channel.id,
                    daily_cap=max(1, int(channel.daily_cap or 1)),
                    quiet_start=channel.quiet_start or "22:00",
                    quiet_end=channel.quiet_end or "08:00",
                    min_gap_minutes=int(channel.min_gap_minutes or 240),
                )
            )


def propose_month(session: Session, now: datetime, *, days: int = 28) -> dict:
    ensure_series(session)
    ensure_plan_settings(session)
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
                settings = session.get(ChannelPlanSettings, channel_id)
                cap = max(1, int((settings.daily_cap if settings else channel.daily_cap) or 1))
                quiet_start = settings.quiet_start if settings else channel.quiet_start
                quiet_end = settings.quiet_end if settings else channel.quiet_end
                placed_today = 0
                for slot in channel.schedule_json or []:
                    if placed_today >= cap:
                        skipped.append({"series": spec["id"], "channel": channel_id, "reason": "daily_cap", "day": day.isoformat()})
                        break
                    when = _msk_slot(day, str(slot))
                    if _quiet(when, quiet_start, quiet_end):
                        skipped.append({"series": spec["id"], "channel": channel_id, "reason": "quiet_hours", "day": day.isoformat()})
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
                    picks, kind = _picks_with_kind(session, channel_id, spec["max_items"], used, now, when)
                    if len(picks) < spec["min_items"]:
                        reason = "not_enough_material"
                        skipped.append(
                            {
                                "series": spec["id"],
                                "channel": channel_id,
                                "day": day.isoformat(),
                                "reason": reason,
                                "have": len(picks),
                                "need": spec["min_items"],
                            }
                        )
                        title = f"Нужен материал на {day.isoformat()} для {channel_id}"
                        if session.query(EditorialTask).filter_by(channel_id=channel_id, title=title).first() is None:
                            session.add(
                                EditorialTask(
                                    kind="research",
                                    channel_id=channel_id,
                                    title=title,
                                    status="open",
                                    reason="слот пуст: нет свежего breaking и подходящего evergreen",
                                )
                            )
                        continue
                    session.add(
                        Episode(
                            series_id=spec["id"],
                            channel_id=channel_id,
                            slot_utc=when,
                            status="proposed",
                            item_refs=picks,
                            reason="evergreen, не выдаётся за свежую новость" if kind == "evergreen" else "dry-run proposal",
                            version=1,
                            origin="propose",
                            format_id=spec["style"],
                            locked=False,
                            program_kind=kind,
                            vacancy_reason="",
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
    picks, _kind = _picks_with_kind(session, channel_id, limit, used, now, slot, allow_evergreen=False)
    return picks


def _picks_with_kind(
    session: Session,
    channel_id: str,
    limit: int,
    used: set[int],
    now: datetime,
    slot: datetime,
    *,
    allow_evergreen: bool = True,
) -> tuple[list[int], str]:
    del now
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
    breaking: list[int] = []
    evergreen: list[int] = []
    for row in rows:
        if row.cluster_id in used or row.cluster_id in breaking or row.cluster_id in evergreen:
            continue
        cluster = session.get(StoryCluster, row.cluster_id)
        if cluster is None or cluster.locked:
            continue
        if cluster.program_kind == "evergreen" or cluster.kind == "evergreen" or cluster.list_name == "evergreen":
            if allow_evergreen and _within_ttl(session, cluster, slot):
                evergreen.append(row.cluster_id)
            continue
        if not _within_ttl(session, cluster, slot):
            continue
        breaking.append(row.cluster_id)
        if len(breaking) >= limit:
            break
    if len(breaking) >= limit:
        return breaking[:limit], "breaking"
    if allow_evergreen and evergreen:
        mixed = breaking + evergreen
        return mixed[:limit], "evergreen" if not breaking else "breaking"
    return breaking[:limit], "breaking"


def _within_ttl(session: Session, cluster: StoryCluster, slot: datetime) -> bool:
    story = _primary_story(session, cluster)
    anchor = story.published_utc if story is not None and story.published_utc is not None else cluster.event_at or cluster.first_seen
    hours = (ensure_utc(slot) - ensure_utc(anchor)).total_seconds() / 3600
    if cluster.program_kind == "evergreen" or cluster.kind == "evergreen":
        return hours <= TTL_HOURS["evergreen"]
    limit = TTL_HOURS.get(cluster.event_type or cluster.kind, TTL_HOURS["event"])
    if cluster.kind == "cve":
        limit = TTL_HOURS["cve"]
    if cluster.kind == "release":
        limit = TTL_HOURS["release"]
    if story is not None and story.is_preprint:
        limit = TTL_HOURS["preprint"]
    return hours <= limit
