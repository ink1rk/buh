"""Financial habits scoring: economy, discipline, regularity, impulsiveness, risk, investing, stability."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import pstdev

from app.models.transaction import Transaction
from app.schemas.habits import HabitScore, HabitsProfile


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def compute_habits(transactions: list[Transaction], monthly_income: float) -> HabitsProfile:
    today = date.today()
    window_start = today - timedelta(days=90)
    recent = [t for t in transactions if t.occurred_on >= window_start]
    expenses = [t for t in recent if t.amount < 0]
    incomes = [t for t in recent if t.amount > 0]

    total_expense = sum(abs(t.amount) for t in expenses)
    total_income = sum(t.amount for t in incomes) or monthly_income * 3

    # Economy: spend less relative to income
    economy = _clamp(100 - (total_expense / max(total_income, 1)) * 100)

    # Discipline: how many of the last 30 days had at least one logged transaction
    days_logged = {t.occurred_on for t in transactions if t.occurred_on >= today - timedelta(days=30)}
    discipline = _clamp(len(days_logged) / 30 * 100)

    # Regularity: coefficient of variation of daily spend (lower variance = more regular)
    daily: dict[date, float] = defaultdict(float)
    for t in expenses:
        daily[t.occurred_on] += abs(t.amount)
    values = list(daily.values())
    if len(values) >= 2 and sum(values) > 0:
        mean = sum(values) / len(values)
        cv = pstdev(values) / max(mean, 1)
        regularity = _clamp(100 - cv * 40)
    else:
        regularity = 50.0

    # Impulsiveness: share of large one-off discretionary purchases (gadgets, restaurants) vs total
    impulsive_categories = {"gadgets", "restaurants", "cafe"}
    impulsive_sum = sum(abs(t.amount) for t in expenses if t.category in impulsive_categories)
    impulsiveness_raw = impulsive_sum / max(total_expense, 1) * 100
    impulsiveness = _clamp(100 - impulsiveness_raw * 1.4)  # higher score = less impulsive

    # Risk: share of capital-like moves into crypto/investment relative to total flow (too much = risky)
    invest_sum = sum(abs(t.amount) for t in recent if t.transaction_type in ("investment",))
    risk_ratio = invest_sum / max(total_income, 1)
    risk_score = _clamp(100 - abs(risk_ratio - 0.15) * 200)  # ideal ~15% of income

    # Investment activity: regularity of investing (months with an investment tx / 3)
    invest_months = {t.occurred_on.strftime("%Y-%m") for t in recent if t.transaction_type == "investment"}
    investment_activity = _clamp(len(invest_months) / 3 * 100)

    # Stability: income variance across months
    income_by_month: dict[str, float] = defaultdict(float)
    for t in incomes:
        income_by_month[t.occurred_on.strftime("%Y-%m")] += t.amount
    inc_values = list(income_by_month.values())
    if len(inc_values) >= 2 and sum(inc_values) > 0:
        mean_i = sum(inc_values) / len(inc_values)
        cv_i = pstdev(inc_values) / max(mean_i, 1)
        stability = _clamp(100 - cv_i * 100)
    else:
        stability = 70.0

    scores = [
        HabitScore(key="economy", label="Экономность", score=round(economy, 1), explanation="Доля дохода, которую вы не тратите."),
        HabitScore(key="discipline", label="Дисциплина", score=round(discipline, 1), explanation="Регулярность ведения учёта за 30 дней."),
        HabitScore(key="regularity", label="Регулярность", score=round(regularity, 1), explanation="Стабильность трат изо дня в день."),
        HabitScore(key="impulsiveness", label="Импульсивность", score=round(impulsiveness, 1), explanation="Чем выше — тем меньше спонтанных покупок."),
        HabitScore(key="risk", label="Риск", score=round(risk_score, 1), explanation="Баланс между ростом капитала и осторожностью."),
        HabitScore(key="investment_activity", label="Инвест. активность", score=round(investment_activity, 1), explanation="Как часто вы инвестируете."),
        HabitScore(key="stability", label="Устойчивость", score=round(stability, 1), explanation="Предсказуемость поступлений дохода."),
    ]

    overall = round(sum(s.score for s in scores) / len(scores), 1)

    if overall >= 80:
        archetype = "Стратег"
        summary = "Ваши привычки работают на вас системно. Продолжайте — капитал растёт почти без усилий."
    elif overall >= 60:
        archetype = "Строитель"
        summary = "Хорошая база. Усильте самое слабое звено — и рост капитала ускорится."
    elif overall >= 40:
        archetype = "Исследователь"
        summary = "Вы в процессе. Сфокусируйтесь на дисциплине и регулярности — остальное подтянется."
    else:
        archetype = "Новичок"
        summary = "Начните с малого: фиксируйте каждую трату 7 дней подряд — это изменит всё."

    return HabitsProfile(scores=scores, overall=overall, archetype=archetype, summary=summary)
