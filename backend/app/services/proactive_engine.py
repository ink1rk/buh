"""Proactive AI + Financial Psychologist.

The core principle from the brief: the AI should not wait to be asked.
It should surface budget pace, investing gaps, upcoming charges, seasonal
patterns, and behavioral triggers (payday spending, weekday overspend) —
unprompted, every day.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.models.calendar import CalendarEvent
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services.ledger import is_income, spending


def _days_in_month(d: date) -> int:
    nxt = d.replace(day=28) + timedelta(days=4)
    return (nxt - timedelta(days=nxt.day)).day


def generate_proactive_alerts(
    transactions: list[Transaction],
    subscriptions: list[Subscription],
    events: list[CalendarEvent],
    monthly_income: float,
    monthly_budget: float,
) -> list[dict]:
    """Unprompted statements the app pushes to the user, not answers to questions."""

    today = date.today()
    alerts: list[dict] = []
    spent = spending(transactions)

    # 1) Budget pace today
    month_start = today.replace(day=1)
    dim = _days_in_month(today)
    spent_month = sum(abs(t.amount) for t in spent if t.occurred_on >= month_start)
    if monthly_budget > 0:
        pace_expected = monthly_budget * (today.day / dim)
        pace_pct = spent_month / monthly_budget * 100
        if spent_month >= monthly_budget * 0.7:
            alerts.append(
                {
                    "icon": "gauge",
                    "title": f"Уже потрачено {pace_pct:.0f}% месячного бюджета",
                    "body": f"На {today.day}-й день месяца вы потратили {spent_month:,.0f} ₽ из {monthly_budget:,.0f} ₽.".replace(",", " "),
                    "tone": "warning" if spent_month > pace_expected * 1.15 else "neutral",
                    "category": "budget_pace",
                }
            )

    # 2) No-invest streak
    last_invest = max((t.occurred_on for t in transactions if t.transaction_type == "investment"), default=None)
    if last_invest:
        gap = (today - last_invest).days
        if gap >= 14:
            alerts.append(
                {
                    "icon": "trending-up",
                    "title": f"Ты уже {gap} дней не инвестировал",
                    "body": "Регулярность важнее суммы. Даже небольшой взнос сегодня поддержит привычку.",
                    "tone": "warning" if gap >= 30 else "neutral",
                    "category": "invest_gap",
                }
            )
    else:
        alerts.append(
            {
                "icon": "trending-up",
                "title": "Вы ещё не инвестировали",
                "body": "Начните с малого — первая инвестиция открывает достижение и новую привычку.",
                "tone": "neutral",
                "category": "invest_gap",
            }
        )

    # 3) Upcoming subscription charges
    horizon = today + timedelta(days=5)
    upcoming_subs = [s for s in subscriptions if s.is_active and s.next_billing_date and today <= s.next_billing_date <= horizon]
    if upcoming_subs:
        total = sum(s.amount for s in upcoming_subs)
        alerts.append(
            {
                "icon": "repeat",
                "title": f"Через 5 дней спишется {len(upcoming_subs)} подписок",
                "body": f"Итого ≈ {total:,.0f} ₽: {', '.join(s.name for s in upcoming_subs[:4])}.".replace(",", " "),
                "tone": "neutral",
                "category": "subscriptions",
            }
        )

    # 4) Seasonal pattern (same month last year vs average)
    this_month_num = today.month
    same_month_last_year = [
        t for t in spent
        if t.occurred_on.month == this_month_num and t.occurred_on.year == today.year - 1
    ]
    other_months = [t for t in spent if t.occurred_on.month != this_month_num]
    if same_month_last_year and other_months:
        avg_season = sum(abs(t.amount) for t in same_month_last_year)
        avg_other_monthly = sum(abs(t.amount) for t in other_months) / max(
            len({(t.occurred_on.year, t.occurred_on.month) for t in other_months}), 1
        )
        if avg_other_monthly > 0 and avg_season >= avg_other_monthly * 1.3:
            alerts.append(
                {
                    "icon": "sun",
                    "title": "Сезонный всплеск расходов",
                    "body": f"В этом месяце в прошлом году расходы были выше обычного на {avg_season / avg_other_monthly * 100 - 100:.0f}%. Возможно, отпуск или сезонные траты — учесть в бюджете?",
                    "tone": "neutral",
                    "category": "seasonal",
                }
            )

    return alerts[:6]


WEEKDAYS_RU = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]


def detect_behavior_patterns(transactions: list[Transaction]) -> list[dict]:
    """The 'financial psychologist' layer — finds *why*, not just *what*."""

    today = date.today()
    window = [t for t in spending(transactions) if t.occurred_on >= today - timedelta(days=90)]
    patterns: list[dict] = []

    # Weekday overspend pattern
    by_weekday: dict[int, list[float]] = defaultdict(list)
    daily_totals: dict[date, float] = defaultdict(float)
    for t in window:
        daily_totals[t.occurred_on] += abs(t.amount)
    for d, total in daily_totals.items():
        by_weekday[d.weekday()].append(total)

    if by_weekday:
        avg_by_weekday = {wd: sum(v) / len(v) for wd, v in by_weekday.items() if v}
        overall_avg = sum(avg_by_weekday.values()) / max(len(avg_by_weekday), 1)
        for wd, avg in avg_by_weekday.items():
            if overall_avg > 0 and avg >= overall_avg * 1.5 and len(by_weekday[wd]) >= 4:
                patterns.append(
                    {
                        "title": f"Каждую {WEEKDAYS_RU[wd]} ты превышаешь обычный бюджет",
                        "body": f"В среднем в этот день расходы на {avg / overall_avg * 100 - 100:.0f}% выше обычного.",
                        "insight_type": "pattern",
                        "severity": "info",
                        "category": "behavior",
                    }
                )
                break  # one weekday pattern is enough signal, avoid noise

    # Delivery frequency trend (2 weeks vs previous 2 weeks)
    delivery = [t for t in window if "достав" in (t.description or "").lower() or (t.merchant or "").lower().find("достав") >= 0]
    last2 = [t for t in delivery if t.occurred_on >= today - timedelta(days=14)]
    prev2 = [t for t in delivery if today - timedelta(days=28) <= t.occurred_on < today - timedelta(days=14)]
    if len(prev2) >= 1 and len(last2) >= len(prev2) * 1.5 and len(last2) >= 3:
        patterns.append(
            {
                "title": "Последние две недели ты чаще заказываешь доставку",
                "body": f"{len(last2)} заказов против {len(prev2)} двумя неделями ранее.",
                "insight_type": "pattern",
                "severity": "info",
                "category": "restaurants",
            }
        )

    # Payday spending spike: find income days, check spend in following 3 days
    incomes = [t for t in transactions
               if is_income(t) and t.occurred_on >= today - timedelta(days=180)]
    spent = spending(transactions)
    for pattern in _payday_spike(incomes, spent):
        patterns.append(pattern)

    return patterns[:3]


# Зарплатой считается крупное поступление. Кэшбэк в пять рублей — тоже доход,
# и покупки того же дня рядом с ним выглядели тратой всей зарплаты: доля
# считалась по каждому поступлению отдельно и усреднялась, поэтому на главной
# висело «в первые 72 часа уходит 93905% дохода».
PAYDAY_SHARE = 0.25
PAYDAYS_FOR_A_PATTERN = 3
PAYDAY_WINDOW_DAYS = 3


def _payday_spike(incomes: list[Transaction], spent: list[Transaction]) -> list[dict]:
    """Сколько зарплаты уходит в первые трое суток после её прихода."""
    if not incomes:
        return []
    biggest = max(t.amount for t in incomes)
    paydays = [t for t in incomes if t.amount >= biggest * PAYDAY_SHARE]
    if len(paydays) < PAYDAYS_FOR_A_PATTERN:
        return []

    # Окна складываются днями, а не долями: две зарплаты подряд иначе
    # засчитали бы одни и те же траты дважды.
    days = {
        pay.occurred_on + timedelta(days=step)
        for pay in paydays
        for step in range(PAYDAY_WINDOW_DAYS + 1)
    }
    earned = sum(t.amount for t in paydays)
    share = sum(abs(t.amount) for t in spent if t.occurred_on in days) / earned
    if share < 0.25:
        return []
    return [
        {
            "title": "После зарплаты в первые три дня уходит значительная часть дохода",
            "body": f"В среднем ≈ {share * 100:.0f}% зарплаты тратится в первые 72 часа "
                    f"после поступления (по {len(paydays)} последним начислениям).",
            "insight_type": "warning",
            "severity": "warning",
            "category": "behavior",
        }
    ]
