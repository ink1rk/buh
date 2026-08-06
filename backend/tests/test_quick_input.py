"""Unit tests — natural language quick input parser."""

import pytest

from app.services.quick_input import parse_quick_input


@pytest.mark.parametrize(
    "text,tx_type,amount,category",
    [
        ("+50000 зарплата", "income", 50000, "salary"),
        ("-1200 пятерочка", "expense", -1200, "groceries"),
        ("-450 кофе", "expense", -450, "cafe"),
        ("долг Саше 3000", "debt", -3000, "debt_owing"),
        ("мне должен Андрей 12000", "debt", 12000, "debt_owed"),
        ("Купил акции 25000", "investment", -25000, "investments"),
        ("Пополнил вклад 10000", "savings", -10000, "savings"),
        ("купил ноутбук 180000", "expense", -180000, "gadgets"),
    ],
)
def test_parse_quick_input(text, tx_type, amount, category):
    draft, confidence, explanation = parse_quick_input(text)
    assert draft.transaction_type == tx_type
    assert draft.amount == amount
    assert draft.category == category
    assert 0.5 <= confidence <= 1.0
    assert explanation


def test_parse_requires_amount():
    with pytest.raises(ValueError):
        parse_quick_input("просто текст без суммы")
