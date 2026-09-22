"""Financial Health Score engine."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.dashboard import FinancialHealth, HealthFactor


@dataclass
class HealthInputs:
    monthly_income: float
    monthly_expense: float
    emergency_fund: float  # reserve + savings liquid
    total_debt: float  # i_owe
    investments: float
    savings_rate: float  # 0..1
    income_stability: float  # 0..1
    investment_regularity: float  # 0..1 months with investments / 6
    discipline_score: float  # 0..1 tracking consistency


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def compute_health(data: HealthInputs) -> FinancialHealth:
    if not any((data.monthly_income, data.monthly_expense, data.emergency_fund,
                data.total_debt, data.investments)):
        # Оценка, посчитанная из нулей, — это приговор человеку, о котором
        # ничего не известно. «48 из 100, требует внимания» на пустой базе
        # выглядит выводом, а на деле не значит ничего.
        return FinancialHealth(
            score=0, label="Пока не о чем судить", factors=[], known=False,
            summary="Добавьте операции или загрузите выписку — оценка появится, "
                    "когда будет что оценивать.")

    income = max(data.monthly_income, 1.0)
    expense = max(data.monthly_expense, 0.0)

    # Emergency fund: target 6 months of expenses
    months_cover = data.emergency_fund / max(expense, 1.0)
    emergency_score = _clamp((months_cover / 6.0) * 100)

    # Debt burden: debt / annual income
    debt_ratio = data.total_debt / (income * 12)
    debt_score = _clamp(100 - debt_ratio * 200)

    # Savings rate
    savings_score = _clamp(data.savings_rate * 250)  # 40% => 100

    # Expense control: expense should be < 80% income
    expense_ratio = expense / income
    expense_score = _clamp(100 - max(0, expense_ratio - 0.7) * 300)

    # Investments regularity
    invest_score = _clamp(data.investment_regularity * 100)

    # Income stability
    stability_score = _clamp(data.income_stability * 100)

    # Debt-to-income monthly
    dti = data.total_debt / (income * 12) if income else 1
    dti_score = _clamp(100 - dti * 180)

    # Discipline
    discipline_score = _clamp(data.discipline_score * 100)

    factors = [
        HealthFactor(name="Подушка безопасности", score=emergency_score, weight=0.18, explanation=f"Покрытие: {months_cover:.1f} мес. расходов (цель — 6)."),
        HealthFactor(name="Долги", score=debt_score, weight=0.14, explanation=f"Долговая нагрузка: {debt_ratio * 100:.1f}% годового дохода."),
        HealthFactor(name="Сбережения", score=savings_score, weight=0.14, explanation=f"Норма сбережений: {data.savings_rate * 100:.0f}%."),
        HealthFactor(name="Контроль расходов", score=expense_score, weight=0.12, explanation=f"Расходы = {expense_ratio * 100:.0f}% дохода."),
        HealthFactor(name="Регулярность инвестиций", score=invest_score, weight=0.12, explanation="Как часто вы инвестируете последние 6 месяцев."),
        HealthFactor(name="Стабильность доходов", score=stability_score, weight=0.10, explanation="Предсказуемость денежных поступлений."),
        HealthFactor(name="Обязательства / доход", score=dti_score, weight=0.10, explanation="Отношение обязательств к годовому доходу."),
        HealthFactor(name="Финансовая дисциплина", score=discipline_score, weight=0.10, explanation="Регулярность учёта и следование плану."),
    ]

    score = int(round(sum(f.score * f.weight for f in factors)))
    score = int(_clamp(score))

    if score >= 85:
        label = "Отлично"
        summary = "Вы на пути к финансовой свободе. Держите курс и увеличивайте инвестиции."
    elif score >= 70:
        label = "Хорошо"
        summary = "Фундамент крепкий. Усильте подушку и регулярность инвестиций."
    elif score >= 50:
        label = "Средне"
        summary = "Есть точки роста: снизьте долговую нагрузку и автоматизируйте сбережения."
    else:
        label = "Требует внимания"
        summary = "Сфокусируйтесь на подушке безопасности и контроле расходов — шаг за шагом."

    return FinancialHealth(score=score, label=label, factors=factors, summary=summary)
