"""Интерфейс русский — значит, русскими должны быть и подсказки в нём.

Категория в базе лежит кодом, и код просачивался в текст: «Рост «health» на
200%» посреди русской страницы. Ещё числа шли без склонений: «2 подключение»,
«2273 операция».
"""

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.categories import category_name
from app.services.insights_engine import generate_insights


def _tx(**kwargs):
    defaults = {
        "amount": -100.0,
        "category": "health",
        "description": "",
        "merchant": "",
        "transaction_type": "expense",
        "occurred_on": date.today(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_category_growth_is_named_in_russian():
    today = date.today()
    month_start = today.replace(day=1)
    last_month = month_start - timedelta(days=1)
    transactions = [
        _tx(amount=-15_000, occurred_on=last_month),
        _tx(amount=-45_000, occurred_on=month_start),
    ]

    growth = [i for i in generate_insights(transactions, [], 100_000) if "Рост" in i["title"]]

    assert growth, "рост втрое подсказкой быть должен"
    assert "здоровье" in growth[0]["title"]
    assert "health" not in growth[0]["title"] + growth[0]["body"]


def test_three_hundred_roubles_more_on_pills_is_not_news():
    """Рост втрое на трёхстах рублях — правда, с которой нечего делать."""
    month_start = date.today().replace(day=1)
    transactions = [
        _tx(amount=-150, occurred_on=month_start - timedelta(days=1)),
        _tx(amount=-450, occurred_on=month_start),
        _tx(amount=-30_000, category="groceries", occurred_on=month_start),
    ]

    assert not [i for i in generate_insights(transactions, [], 100_000) if "Рост" in i["title"]]


def test_an_unknown_category_is_shown_as_is_rather_than_lost():
    assert category_name("crypto_mining") == "crypto_mining"
    assert category_name("") == "без категории"
