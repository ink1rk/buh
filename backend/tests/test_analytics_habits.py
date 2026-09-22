"""Unit tests — cashflow conservation, habits, forecast bands, scenarios."""

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.analytics_engine import build_analytics
from app.services.forecast_engine import build_forecast, run_scenario
from app.schemas.analytics import ScenarioRequest
from app.services.habits_engine import compute_habits


def _tx(**kwargs):
    defaults = {
        "id": 1,
        "amount": -100,
        "category": "other",
        "description": "",
        "merchant": "",
        "transaction_type": "expense",
        "occurred_on": date.today(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _acc(account_type, balance):
    return SimpleNamespace(account_type=account_type, balance=balance)


def test_cashflow_is_conserved():
    today = date.today()
    month_start = today.replace(day=1)
    txs = [
        _tx(amount=200_000, transaction_type="income", occurred_on=month_start, category="salary"),
        _tx(amount=-40_000, transaction_type="expense", occurred_on=today, category="groceries"),
        _tx(amount=-20_000, transaction_type="investment", occurred_on=today, category="investments"),
        _tx(amount=-10_000, transaction_type="savings", occurred_on=today, category="savings"),
    ]
    accounts = [_acc("investment", 100_000), _acc("savings", 50_000), _acc("card", 30_000)]
    bundle = build_analytics(txs, accounts, days=30)
    nodes = {n.id: n.amount for n in bundle.cashflow.nodes}
    out = sum(l.value for l in bundle.cashflow.links if l.source == "distribute")
    assert abs(nodes["income"] - nodes["distribute"]) < 0.01
    assert abs(out - nodes["income"]) < 0.01
    assert nodes["expense"] == 40_000
    assert nodes["invest"] == 20_000
    assert nodes["savings"] == 10_000
    assert nodes["free"] == 130_000


def test_analytics_excludes_investments_from_expense_categories():
    today = date.today()
    txs = [
        _tx(amount=100_000, transaction_type="income", occurred_on=today, category="salary"),
        _tx(amount=-5_000, transaction_type="expense", occurred_on=today, category="cafe"),
        _tx(amount=-50_000, transaction_type="investment", occurred_on=today, category="investments"),
    ]
    bundle = build_analytics(txs, [_acc("card", 1)], days=7)
    names = {c.name for c in bundle.by_category}
    # Категории подписаны по-русски: на диаграмме их читает человек.
    assert "кофе и перекусы" in names
    assert "инвестиции" not in names


def test_habits_impulsiveness_not_collapsed():
    today = date.today()
    txs = []
    for i in range(30):
        txs.append(
            _tx(
                amount=200_000 if i % 10 == 0 else 0,
                transaction_type="income",
                occurred_on=today - timedelta(days=i),
                category="salary",
            )
        )
        txs.append(
            _tx(
                amount=-1_500,
                transaction_type="expense",
                occurred_on=today - timedelta(days=i),
                category="groceries",
            )
        )
        if i % 5 == 0:
            txs.append(
                _tx(
                    amount=-450,
                    transaction_type="expense",
                    occurred_on=today - timedelta(days=i),
                    category="cafe",
                )
            )
    # filter zero-income noise
    txs = [t for t in txs if t.amount != 0]
    profile = compute_habits(txs, monthly_income=200_000)
    imp = next(s for s in profile.scores if s.key == "impulsiveness")
    assert imp.score >= 40  # occasional coffee must not crush the score
    assert 0 <= profile.overall <= 100


def test_forecast_series_and_scenario_ordering():
    fc = build_forecast(balance=1_000_000, monthly_income=200_000, monthly_expense=100_000)
    assert len(fc.series) == 36
    assert fc.year_end_balance > 0

    sc = run_scenario(
        ScenarioRequest(scenario="raise", months=12),
        balance=1_000_000,
        monthly_income=200_000,
        monthly_expense=100_000,
    )
    opt = sc.optimistic[-1].optimistic
    base = sc.base[-1].base
    stress = sc.stress[-1].stress
    assert stress <= base <= opt
    assert sc.recommendations
