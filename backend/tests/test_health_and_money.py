"""Unit tests — health score + money-in-days humanizer."""

from app.services.health_score import HealthInputs, compute_health
from app.services.money_in_days import humanize, phrase
from app.services.purchase_analyzer import analyze_purchase


def test_health_score_weights_and_bounds():
    result = compute_health(
        HealthInputs(
            monthly_income=200_000,
            monthly_expense=80_000,
            emergency_fund=480_000,  # 6 months
            total_debt=0,
            investments=300_000,
            savings_rate=0.3,
            income_stability=0.9,
            investment_regularity=0.8,
            discipline_score=0.9,
        )
    )
    assert 0 <= result.score <= 100
    assert abs(sum(f.weight for f in result.factors) - 1.0) < 1e-6
    recomputed = round(sum(f.score * f.weight for f in result.factors))
    assert abs(recomputed - result.score) <= 1
    assert result.score >= 70


def test_health_score_punishes_debt_and_no_cushion():
    weak = compute_health(
        HealthInputs(
            monthly_income=100_000,
            monthly_expense=95_000,
            emergency_fund=5_000,
            total_debt=500_000,
            investments=0,
            savings_rate=0.05,
            income_stability=0.4,
            investment_regularity=0.0,
            discipline_score=0.2,
        )
    )
    strong = compute_health(
        HealthInputs(
            monthly_income=200_000,
            monthly_expense=70_000,
            emergency_fund=600_000,
            total_debt=0,
            investments=400_000,
            savings_rate=0.35,
            income_stability=0.95,
            investment_regularity=1.0,
            discipline_score=0.95,
        )
    )
    assert weak.score < strong.score
    assert weak.score < 55


def test_money_in_days_math():
    life = humanize(amount=160_000, hourly_rate=1000, monthly_savings=40_000, total_capital=1_600_000)
    assert life.work_hours == 160.0
    assert life.life_days == 20.0
    assert life.months_of_savings == 4.0
    assert life.capital_pct == 10.0
    assert life.coffee_equivalent == round(160_000 / 350)
    assert "кофе" in phrase(life)


def test_purchase_analyzer_argues_and_uses_capital():
    result = analyze_purchase(
        item="MacBook",
        price=250_000,
        total_capital=1_000_000,
        hourly_rate=1250,
        monthly_savings=40_000,
        main_goal_remaining=300_000,
        related_memory="Хотел монитор месяц назад",
    )
    assert result.capital_pct == 25.0
    assert result.score < 50  # expensive relative to capital
    assert len(result.challenge_questions) >= 3
    assert result.twin_opinion
    assert "монитор" in " ".join(result.challenge_questions) or result.related_memory
    assert result.coffee_equivalent > 0
