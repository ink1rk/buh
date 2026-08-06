"""Humanize money: turn amounts into work hours, life days, coffee cups.

Core idea from the brief: don't show "250 000 ₽" — show "18 рабочих дней".
This makes the cost of a purchase visceral instead of abstract.
"""

from __future__ import annotations

from dataclasses import dataclass

AVG_COFFEE_PRICE = 350.0
WORK_HOURS_PER_DAY = 8.0


@dataclass
class MoneyInLife:
    work_hours: float
    life_days: float
    months_of_savings: float
    coffee_equivalent: int
    capital_pct: float


def humanize(
    amount: float,
    hourly_rate: float,
    monthly_savings: float,
    total_capital: float,
) -> MoneyInLife:
    hourly = max(hourly_rate, 1.0)
    work_hours = amount / hourly
    life_days = work_hours / WORK_HOURS_PER_DAY
    months = amount / max(monthly_savings, 1.0)
    coffee = int(round(amount / AVG_COFFEE_PRICE))
    capital_pct = amount / max(total_capital, 1.0) * 100
    return MoneyInLife(
        work_hours=round(work_hours, 1),
        life_days=round(life_days, 1),
        months_of_savings=round(months, 1),
        coffee_equivalent=coffee,
        capital_pct=round(capital_pct, 2),
    )


def phrase(life: MoneyInLife, item_investments_count: int | None = None) -> str:
    parts = [f"{life.life_days:.0f} рабочих дней", f"{life.months_of_savings:.1f} мес. накоплений"]
    if item_investments_count:
        parts.append(f"{item_investments_count} обычных инвестиций")
    parts.append(f"{life.coffee_equivalent} чашек кофе")
    return " · ".join(parts)
