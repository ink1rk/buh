"""Перевод себе — не трата, и подсказки на главной это должны знать.

В годовой выписке переводов между своими счетами оказалось на 1,7 млн —
вдвое больше всех настоящих трат за год. Посчитанные расходом, они делали
неверной каждую подсказку: «уже потрачено 385% бюджета месяца» при расходе
месяца в 26 тысяч.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.ledger import is_income, is_spending, spending
from app.services.proactive_engine import (
    detect_behavior_patterns,
    generate_proactive_alerts,
)


def _tx(**kwargs):
    defaults = {
        "amount": -100.0,
        "category": "other",
        "description": "",
        "merchant": "",
        "transaction_type": "expense",
        "occurred_on": date.today(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_moving_money_is_neither_spending_nor_income():
    out = _tx(amount=-50_000, transaction_type="transfer")
    back = _tx(amount=50_000, transaction_type="transfer")
    deposit = _tx(amount=-30_000, transaction_type="savings")
    purchase = _tx(amount=-900, transaction_type="expense")
    salary = _tx(amount=52_000, transaction_type="income")

    assert not any(is_spending(t) for t in (out, back, deposit, salary))
    assert is_spending(purchase)
    assert is_income(salary) and not is_income(back)
    assert spending([out, back, deposit, purchase, salary]) == [purchase]


def test_budget_pace_counts_purchases_not_transfers():
    today = date.today()
    transactions = [
        _tx(amount=-8_000, occurred_on=today.replace(day=1)),
        _tx(amount=-76_000, transaction_type="transfer", occurred_on=today),
    ]

    alerts = generate_proactive_alerts(transactions, [], [], 40_000, 30_000)
    pace = next((a for a in alerts if a["category"] == "budget_pace"), None)

    assert pace is None, "8 000 из 30 000 — это не повод для предупреждения"


def test_budget_pace_is_silent_until_there_is_a_budget():
    """Расходы этого же месяца бюджетом быть не могут.

    Иначе сравнение сводится к «потрачено 100% того, что потрачено», и
    предупреждение о перерасходе появляется всегда.
    """
    transactions = [_tx(amount=-26_000, occurred_on=date.today())]

    alerts = generate_proactive_alerts(transactions, [], [], 0, 0)

    assert not [a for a in alerts if a["category"] == "budget_pace"]


def test_payday_pattern_ignores_money_moved_on_payday():
    """В день зарплаты деньги обычно перекладывают на другой счёт.

    Принятое за траты, это объявляло бы человеку, что он сливает зарплату в
    первые три дня.
    """
    payday = date.today() - timedelta(days=10)
    transactions = [
        _tx(amount=60_000, transaction_type="income", occurred_on=payday),
        _tx(amount=-55_000, transaction_type="transfer", occurred_on=payday),
        _tx(amount=-500, occurred_on=payday + timedelta(days=1)),
    ]

    patterns = detect_behavior_patterns(transactions)

    assert not [p for p in patterns if "зарплаты" in p["title"]]
