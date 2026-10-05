"""Разбор смотрит на полные месяцы выписки и называет, куда уходят деньги."""

from datetime import date
from types import SimpleNamespace

from app.services.review_engine import build_review, reclassify_unclear

TODAY = date(2026, 3, 15)


def tx(day, amount, **kwargs):
    return SimpleNamespace(
        amount=amount,
        category=kwargs.get("category", "salary" if amount > 0 else "other"),
        description=kwargs.get("description", ""),
        merchant=kwargs.get("merchant", ""),
        transaction_type=kwargs.get(
            "transaction_type", "income" if amount > 0 else "expense"
        ),
        occurred_on=day,
    )


def _year():
    rows = []
    for month in (10, 11, 12, 1):
        year = 2025 if month >= 10 else 2026
        day = date(year, month, 3)
        rows.append(tx(day, 200_000, category="salary"))
        rows.append(tx(
            day, -40_000, category="transport",
            merchant="DELIMOBIL MOSCOW MOSCOW RU",
            description="DELIMOBIL MOSCOW MOSCOW RU",
        ))
        rows.append(tx(day, -10_000, category="groceries", merchant="Магнит"))
        rows.append(tx(day, -120_000, category="transfers", transaction_type="transfer"))
    # Обрывок текущего месяца не должен стать «нормой».
    rows.append(tx(date(2026, 3, 10), -500_000, category="shopping", merchant="Разовая"))
    return rows


def test_the_review_uses_complete_months_and_names_the_biggest_place():
    review = build_review(_year(), today=TODAY)

    assert review.ready
    assert review.months == 4
    assert review.earned_month == 200_000
    assert review.spent_month == 50_000
    assert review.left_month == 150_000
    assert review.savings_rate == 0.75
    assert review.transfers_month == 120_000
    text = " ".join(note.title + note.body for note in review.advice)
    assert "Делимобиль" in text
    assert "Переводы" in text
    assert "500 000" not in text
    assert "Стабильный день" not in text


def test_a_terminal_code_is_counted_as_the_shop_it_is():
    rows = []
    for month in (1, 2):
        day = date(2026, month, 4)
        rows.append(tx(day, 100_000, category="salary"))
        rows.append(tx(
            day, -8_000, category="other",
            merchant="VV_8348_KCO_4 MOSCOW RU",
            description="VV_8348_KCO_4 MOSCOW RU",
        ))
    review = build_review(rows, today=date(2026, 3, 20))

    assert review.categories[0].name == "продукты"
    assert review.counterparties[0].name == "ВкусВилл"


def test_an_opening_stub_does_not_set_the_average():
    rows = [
        tx(date(2025, 9, 21), -400_000, category="travel"),
        tx(date(2025, 10, 2), 100_000, category="salary"),
        tx(date(2025, 10, 2), -20_000, category="groceries"),
        tx(date(2025, 11, 2), 100_000, category="salary"),
        tx(date(2025, 11, 2), -20_000, category="groceries"),
    ]
    review = build_review(rows, today=date(2025, 12, 10))

    assert review.ready
    assert review.months == 2
    assert review.spent_month == 20_000


def test_without_two_full_months_there_is_no_fake_praise():
    empty = build_review([], today=TODAY)
    assert empty.ready is False
    assert "не загружена" in empty.headline

    short = build_review(
        [tx(date(2026, 3, 1), 50_000), tx(date(2026, 3, 2), -10_000)],
        today=TODAY,
    )
    assert short.ready is False
    assert short.advice == []


def test_known_merchants_leave_the_other_bucket():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE transactions (id integer, amount real, merchant text, "
        "description text, category text)"
    )
    conn.execute(
        "INSERT INTO transactions VALUES (1, -100, 'VV_1 MOSCOW RU', 'VV_1 MOSCOW RU', 'other')"
    )
    conn.execute(
        "INSERT INTO transactions VALUES (2, -50, 'OLDBOY MOSCOW RU', 'OLDBOY MOSCOW RU', 'other')"
    )

    class Conn:
        def exec_driver_sql(self, sql, params=None):
            return conn.execute(sql, params or ())

    assert reclassify_unclear(Conn()) == 1
    assert conn.execute("SELECT category FROM transactions WHERE id=1").fetchone()[0] == "groceries"
    assert conn.execute("SELECT category FROM transactions WHERE id=2").fetchone()[0] == "other"
