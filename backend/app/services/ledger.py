"""Что в истории операций считать тратой и доходом.

Перевод себе, взнос на вклад и покупка бумаг уменьшают счёт, но тратой не
являются: посчитанные расходом, они превращают перекладывание денег из кармана
в карман в потребление. В годовой выписке таких переводов оказалось на 1,7 млн
— вдвое больше всех настоящих трат за год, и подсказки на главной странице
считались от этой суммы: «уже потрачено 385% бюджета месяца».

Определение одно на всё приложение. Пока каждый счёт считал по-своему,
страница противоречила сама себе: в балансах расход месяца был один, а в
подсказке под ним — вчетверо больше.
"""

from __future__ import annotations

from typing import Protocol


class Entry(Protocol):
    amount: float
    transaction_type: str


# Пустой тип — это операция, заведённая до появления типов; она расход.
SPEND_TYPES = frozenset({"expense", ""})


def is_spending(entry: Entry) -> bool:
    return entry.amount < 0 and entry.transaction_type in SPEND_TYPES


def is_income(entry: Entry) -> bool:
    return entry.amount > 0 and entry.transaction_type == "income"


def spending(entries: list[Entry]) -> list[Entry]:
    return [entry for entry in entries if is_spending(entry)]
