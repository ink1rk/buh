"""Месячный план расходов: конверты по категориям и факт из выписки.

Пока плана нет, приложение умеет только показывать, что уже случилось.
Человеку из этого не собрать бюджет: цифры есть, а «сколько можно
в этом месяце» — нет. Конверты — объявленные лимиты. Предложение
считается по среднему за доступные месяцы истории, без переводов
и накоплений: это не потребление.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import BudgetEnvelope
from app.models.transaction import Transaction
from app.models.user import UserProfile
from app.schemas.budget import (
    BudgetEnvelopeIn,
    BudgetEnvelopeOut,
    BudgetGlance,
    BudgetPlan,
    BudgetSuggestion,
    BudgetTotals,
)
from app.services.categories import category_color, category_name
from app.services.ledger import is_income, is_spending

HISTORY_MONTHS = 12
MIN_PROPOSE = 50.0
# Черновик не должен сразу быть больше дохода: иначе «распределить месяц»
# предлагает план, который заведомо не сходится.
PLAN_SHARE_OF_INCOME = 0.8


def _nice(amount: float) -> float:
    """Круглое число, чтобы править план, а не копейки из среднего."""
    if amount <= 0:
        return 0.0
    if amount < 500:
        step = 50
    elif amount < 5_000:
        step = 100
    else:
        step = 500
    return float(max(step, round(amount / step) * step))


def _month_key(day: date) -> str:
    return day.strftime("%Y-%m")


def _days_in_month(today: date) -> int:
    nxt = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    return (nxt - today.replace(day=1)).days


def _pace_pct(spent: float, limit: float, today: date | None = None) -> float:
    if limit <= 0:
        return 0.0
    today = today or date.today()
    expected = limit * (today.day / _days_in_month(today))
    if expected <= 0:
        return 0.0
    return round(spent / expected * 100, 1)


async def history_averages(db: AsyncSession, months: int = HISTORY_MONTHS) -> tuple[dict[str, float], int, float]:
    """Среднее в месяц по категории и средний доход за окно истории."""
    today = date.today()
    start = today.replace(day=1) - relativedelta(months=months)
    rows = list(
        (await db.execute(select(Transaction).where(Transaction.occurred_on >= start))).scalars()
    )
    spend_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    income_month: dict[str, float] = defaultdict(float)
    active_months: set[str] = set()
    for row in rows:
        key = _month_key(row.occurred_on)
        active_months.add(key)
        if is_spending(row):
            spend_month[row.category or "other"][key] += abs(row.amount)
        elif is_income(row):
            income_month[key] += row.amount
    observed = len(active_months)
    divisor = max(observed, 1)
    averages = {category: sum(per_month.values()) / divisor for category, per_month in spend_month.items()}
    suggested_income = sum(income_month.values()) / divisor if income_month else 0.0
    return averages, observed, round(suggested_income, 2)


async def spent_this_month(db: AsyncSession) -> dict[str, float]:
    today = date.today()
    start = today.replace(day=1)
    rows = list(
        (await db.execute(select(Transaction).where(Transaction.occurred_on >= start))).scalars()
    )
    by_cat: dict[str, float] = defaultdict(float)
    for row in rows:
        if is_spending(row):
            by_cat[row.category or "other"] += abs(row.amount)
    return dict(by_cat)


def scale_limits(limits: dict[str, float], income: float) -> dict[str, float]:
    """Ужать предложенные лимиты, если в сумме они больше доли дохода."""
    if income <= 0:
        return limits
    total = sum(limits.values())
    target = income * PLAN_SHARE_OF_INCOME
    if total <= 0 or total <= target:
        return {category: _nice(amount) for category, amount in limits.items()}
    factor = target / total
    return {category: _nice(amount * factor) for category, amount in limits.items()}


async def list_envelopes(db: AsyncSession) -> list[BudgetEnvelope]:
    rows = list(
        (
            await db.execute(
                select(BudgetEnvelope)
                .where(BudgetEnvelope.is_active.is_(True))
                .order_by(BudgetEnvelope.id)
            )
        ).scalars()
    )
    return rows


def _envelope_out(
    row: BudgetEnvelope,
    spent: float,
    average: float,
) -> BudgetEnvelopeOut:
    return BudgetEnvelopeOut(
        id=row.id,
        category=row.category,
        name=category_name(row.category),
        color=category_color(row.category),
        monthly_limit=round(row.monthly_limit, 2),
        spent_this_month=round(spent, 2),
        average_last_12m=round(average, 2),
        remaining=round(row.monthly_limit - spent, 2),
        pace_pct=_pace_pct(spent, row.monthly_limit),
    )


async def build_plan(db: AsyncSession, profile: UserProfile) -> BudgetPlan:
    averages, observed, suggested_income = await history_averages(db)
    spent = await spent_this_month(db)
    envelopes = await list_envelopes(db)
    planned = [ _envelope_out(row, spent.get(row.category, 0.0), averages.get(row.category, 0.0)) for row in envelopes ]
    taken = {row.category for row in envelopes}
    raw = {
        category: average
        for category, average in averages.items()
        if category not in taken and average >= MIN_PROPOSE
    }
    income_for_draft = profile.monthly_income or suggested_income
    proposed = scale_limits(raw, income_for_draft)
    suggestions = []
    for category, average in sorted(raw.items(), key=lambda item: -item[1]):
        suggestions.append(
            BudgetSuggestion(
                category=category,
                name=category_name(category),
                color=category_color(category),
                average_last_12m=round(average, 2),
                proposed_limit=proposed.get(category, _nice(average)),
                spent_this_month=round(spent.get(category, 0.0), 2),
            )
        )
    planned_total = sum(item.monthly_limit for item in planned)
    spent_total = sum(spent.values())
    income = profile.monthly_income or 0.0
    return BudgetPlan(
        monthly_income=round(income, 2),
        suggested_income=suggested_income,
        months_observed=observed,
        has_plan=bool(envelopes),
        envelopes=planned,
        suggestions=suggestions,
        totals=BudgetTotals(
            planned=round(planned_total, 2),
            spent=round(spent_total, 2),
            remaining=round(planned_total - spent_total, 2),
            unallocated=round(income - planned_total, 2) if income else 0.0,
        ),
    )


async def replace_plan(
    db: AsyncSession,
    profile: UserProfile,
    envelopes: list[BudgetEnvelopeIn],
    monthly_income: float | None = None,
) -> BudgetPlan:
    existing = list((await db.execute(select(BudgetEnvelope))).scalars())
    for row in existing:
        await db.delete(row)
    await db.flush()
    seen: set[str] = set()
    for item in envelopes:
        slug = (item.category or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        db.add(BudgetEnvelope(category=slug, monthly_limit=max(item.monthly_limit, 0.0)))
    if monthly_income is not None:
        profile.monthly_income = monthly_income
    await db.flush()
    return await build_plan(db, profile)


async def seed_from_history(
    db: AsyncSession,
    profile: UserProfile,
    *,
    replace: bool = False,
) -> BudgetPlan:
    existing = await list_envelopes(db)
    if existing and not replace:
        return await build_plan(db, profile)
    averages, _, suggested_income = await history_averages(db)
    income = profile.monthly_income if profile.monthly_income else suggested_income
    raw = {category: average for category, average in averages.items() if average >= MIN_PROPOSE}
    limits = scale_limits(raw, income)
    payload = [
        BudgetEnvelopeIn(category=category, monthly_limit=limit)
        for category, limit in limits.items()
        if limit > 0
    ]
    return await replace_plan(db, profile, payload, monthly_income=income or None)


async def glance(db: AsyncSession, profile: UserProfile, spent_month: float) -> BudgetGlance:
    envelopes = await list_envelopes(db)
    planned = sum(row.monthly_limit for row in envelopes)
    return BudgetGlance(
        has_plan=bool(envelopes),
        planned=round(planned, 2),
        spent=round(spent_month, 2),
        remaining=round(planned - spent_month, 2) if envelopes else 0.0,
        monthly_income=round(profile.monthly_income or 0.0, 2),
    )


async def declared_monthly_budget(db: AsyncSession, profile: UserProfile) -> float:
    """Лимит для подсказок: сумма конвертов, иначе 75% объявленного дохода."""
    envelopes = await list_envelopes(db)
    if envelopes:
        return sum(row.monthly_limit for row in envelopes)
    return profile.monthly_income * 0.75 if profile.monthly_income else 0.0
