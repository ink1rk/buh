"""Financial risk radar: job loss, cash gap, credit load, cushion, big expenses, inflation."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.calendar import CalendarEvent
from app.schemas.habits import RiskItem, RisksProfile


def _status(level: float) -> str:
    if level >= 66:
        return "high"
    if level >= 33:
        return "medium"
    return "low"


def compute_risks(
    monthly_income: float,
    monthly_expense: float,
    reserve: float,
    total_debt: float,
    income_sources: int,
    upcoming_events: list[CalendarEvent],
    liquid_balance: float,
) -> RisksProfile:
    income = max(monthly_income, 1.0)

    # Job loss risk: fewer income sources = higher risk
    job_loss = 80 if income_sources <= 1 else (45 if income_sources == 2 else 20)

    # Cash gap risk: runway in months from reserve vs expense
    months_cover = reserve / max(monthly_expense, 1.0)
    cash_gap = max(0.0, 100 - months_cover * 20)

    # Credit load risk: debt vs annual income
    credit_load = min(100.0, total_debt / (income * 12) * 220)

    # Cushion risk: inverse of months_cover, capped
    cushion_risk = max(0.0, 100 - months_cover / 6 * 100)

    # Big expenses risk: upcoming calendar payments in next 30 days vs liquid balance
    horizon = date.today() + timedelta(days=30)
    upcoming_sum = sum(e.amount for e in upcoming_events if e.event_date <= horizon and e.amount > 0)
    big_expense_risk = min(100.0, upcoming_sum / max(liquid_balance, 1.0) * 100)

    # Inflation risk: static but informative — erodes purchasing power of idle cash
    inflation_risk = 55.0

    items = [
        RiskItem(key="job_loss", label="Риск потери дохода", level=round(job_loss, 1), status=_status(job_loss), explanation=f"Источников дохода: {income_sources}. Диверсификация снижает риск."),
        RiskItem(key="cash_gap", label="Риск кассового разрыва", level=round(cash_gap, 1), status=_status(cash_gap), explanation=f"Подушка покрывает {months_cover:.1f} мес. расходов."),
        RiskItem(key="credit_load", label="Риск кредитной нагрузки", level=round(credit_load, 1), status=_status(credit_load), explanation=f"Долг = {total_debt / max(income, 1):.1f}× месячного дохода."),
        RiskItem(key="cushion", label="Риск недостаточной подушки", level=round(cushion_risk, 1), status=_status(cushion_risk), explanation="Цель — 6 месяцев расходов в резерве."),
        RiskItem(key="big_expenses", label="Риск крупных расходов", level=round(big_expense_risk, 1), status=_status(big_expense_risk), explanation=f"Платежи на 30 дней: {upcoming_sum:,.0f} ₽".replace(",", " ")),
        RiskItem(key="inflation", label="Риск инфляции", level=inflation_risk, status=_status(inflation_risk), explanation="Свободный кэш без инвестирования теряет 6-10% покупательной способности в год."),
    ]

    overall = round(sum(i.level for i in items) / len(items), 1)
    if overall >= 60:
        summary = "Риск-профиль повышенный. В приоритете: подушка и снижение долговой нагрузки."
    elif overall >= 35:
        summary = "Умеренный риск. Есть точки роста, но фундамент держится."
    else:
        summary = "Риски под контролем. Хороший момент подумать о доходности выше инфляции."

    return RisksProfile(items=items, overall_risk=overall, summary=summary)
