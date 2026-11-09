from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.timeutil import ensure_utc, in_quiet_hours, msk_day_bounds, slot_to_utc


@dataclass
class DueItem:
    due_utc: datetime
    published_at: datetime | None
    channel_id: str


def slot_due(now: datetime, schedule: list[str], tz_name: str = "Europe/Moscow", window_minutes: int = 10) -> bool:
    moment = ensure_utc(now)
    for slot in schedule:
        slot_utc = slot_to_utc(moment, slot, tz_name)
        delta = abs((moment - slot_utc).total_seconds())
        if delta <= window_minutes * 60:
            return True
    return False


def select_sendable(items: list[DueItem], now: datetime, *, fresh_hours: int = 36, limit: int = 1) -> list[DueItem]:
    moment = ensure_utc(now)
    cutoff = moment - timedelta(hours=fresh_hours)
    eligible = []
    for item in items:
        due = ensure_utc(item.due_utc)
        published = ensure_utc(item.published_at) if item.published_at else None
        if due > moment:
            continue
        if due < cutoff:
            continue
        if published is None or published < cutoff:
            continue
        eligible.append(item)
    eligible.sort(key=lambda item: ensure_utc(item.due_utc))
    return eligible[:limit]


def gap_ok(existing: list[datetime], due: datetime, min_gap_minutes: int) -> bool:
    for other in existing:
        if abs((ensure_utc(other) - ensure_utc(due)).total_seconds()) < min_gap_minutes * 60:
            return False
    return True


def quiet(now: datetime, start: str = "22:00", end: str = "08:00") -> bool:
    return in_quiet_hours(now, start, end)


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    return msk_day_bounds(now)
