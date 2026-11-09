from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return ensure_utc(parsed)


def slot_to_utc(day: datetime, hhmm: str, tz_name: str = "Europe/Moscow") -> datetime:
    """Convert a local clock slot on `day`'s calendar date to UTC.

    Uses the IANA zone database, so zones that observe DST shift correctly.
    Europe/Moscow has stayed on UTC+3 since 2014.
    """
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    local_day = day.astimezone(ZoneInfo(tz_name)) if day.tzinfo else day
    local = datetime(
        local_day.year,
        local_day.month,
        local_day.day,
        hour,
        minute,
        tzinfo=ZoneInfo(tz_name),
    )
    return local.astimezone(timezone.utc)


def in_quiet_hours(moment: datetime, start: str = "22:00", end: str = "08:00", tz_name: str = "Europe/Moscow") -> bool:
    local = ensure_utc(moment).astimezone(ZoneInfo(tz_name))
    minutes = local.hour * 60 + local.minute

    def to_minutes(hhmm: str) -> int:
        hour, minute = (int(part) for part in hhmm.split(":", 1))
        return hour * 60 + minute

    start_m = to_minutes(start)
    end_m = to_minutes(end)
    if start_m == end_m:
        return False
    if start_m > end_m:
        return minutes >= start_m or minutes < end_m
    return start_m <= minutes < end_m


def msk_day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    local = ensure_utc(moment).astimezone(MSK)
    start = datetime(local.year, local.month, local.day, tzinfo=MSK)
    from datetime import timedelta

    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
