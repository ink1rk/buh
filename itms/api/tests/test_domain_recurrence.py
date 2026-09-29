from datetime import date

from itms.domain.recurrence import next_date


def test_weekly_skips_to_the_following_weekday() -> None:
    monday = next_date("weekly", after=date(2026, 9, 22), weekday=0, inclusive=True)
    assert monday == date(2026, 9, 28)
    assert next_date("weekly", after=monday, weekday=0) == date(2026, 10, 5)


def test_monthly_uses_the_day_and_stays_inside_the_month() -> None:
    assert next_date("monthly", after=date(2026, 9, 22), month_day=15) == date(2026, 10, 15)
    assert next_date("monthly", after=date(2026, 1, 31), month_day=31) == date(2026, 2, 28)


def test_daily_steps_forward() -> None:
    assert next_date("daily", after=date(2026, 9, 22), interval=2) == date(2026, 9, 24)
