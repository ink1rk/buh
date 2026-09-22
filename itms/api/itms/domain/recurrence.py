"""Следующая дата повторяющейся задачи.

Новый экземпляр считается от определения, а не копированием закрытой задачи.
"""

from __future__ import annotations

from datetime import date, timedelta

CADENCES = ("daily", "weekly", "monthly")


def next_date(
    cadence: str,
    *,
    after: date,
    interval: int = 1,
    weekday: int | None = None,
    month_day: int | None = None,
    inclusive: bool = False,
) -> date:
    """Ближайшая дата. inclusive=True оставляет `after`, если она сама подходит."""
    step = max(1, min(int(interval), 366))
    if cadence == "daily":
        return after if inclusive else after + timedelta(days=step)
    if cadence == "weekly":
        target = 0 if weekday is None else int(weekday) % 7
        delta = (target - after.weekday()) % 7
        if delta == 0 and not inclusive:
            delta = 7
        candidate = after + timedelta(days=delta)
        if step > 1 and not (inclusive and delta == 0):
            candidate += timedelta(weeks=step - 1)
        return candidate
    if cadence == "monthly":
        day = int(month_day or after.day)
        year, month = after.year, after.month
        candidate = _month_day(year, month, day)
        if candidate < after or (candidate == after and not inclusive):
            index = (year * 12 + month - 1) + step
            year, month_index = divmod(index, 12)
            candidate = _month_day(year, month_index + 1, day)
        return candidate
    raise ValueError(cadence)


def _month_day(year: int, month: int, day: int) -> date:
    from calendar import monthrange

    return date(year, month, min(day, monthrange(year, month)[1]))
