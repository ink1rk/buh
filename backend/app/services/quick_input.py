"""Natural-language transaction parser (rule-based + optional LLM)."""

from __future__ import annotations

import re
from datetime import date

from app.schemas.transaction import TransactionCreate

AMOUNT_RE = re.compile(
    r"(?<!\d)([+-]?\d[\d\s]{0,12}(?:[.,]\d{1,2})?)\s*(?:₽|руб(?:лей|ля|ль)?|rub|р\.?)?",
    re.IGNORECASE,
)

INCOME_KEYWORDS = (
    "зарплата", "зп", "аванс", "премия", "доход", "вернули", "возврат",
    "фриланс", "кешбек", "кэшбек", "дивиденд", "перевод мне", "+",
)
EXPENSE_KEYWORDS = (
    "купил", "купила", "потратил", "кофе", "пятерочка", "магнит", "ресторан",
    "такси", "uber", "яндекс", "обед", "ужин", "подписка", "-",
)
DEBT_I_OWE = ("долг ", "должен ", "занял у", "взял в долг")
DEBT_OWED = ("мне должен", "должен мне", "одолжил", "дал в долг")
INVEST_KW = ("акци", "etf", "облигац", "портфел", "инвест", "купил акции")
SAVINGS_KW = ("вклад", "накопительн", "пополнил вклад", "резерв", "подушка")

CATEGORY_MAP = {
    "кофе": "cafe",
    "пятерочка": "groceries",
    "магнит": "groceries",
    "перекрёсток": "groceries",
    "перекресток": "groceries",
    "ресторан": "restaurants",
    "такси": "transport",
    "метро": "transport",
    "бензин": "transport",
    "зарплата": "salary",
    "аренда": "housing",
    "квартира": "housing",
    "нетфликс": "subscriptions",
    "spotify": "subscriptions",
    "аптека": "health",
    "спорт": "health",
    "ноутбук": "gadgets",
    "iphone": "gadgets",
    "macbook": "gadgets",
}


def _parse_amount(text: str) -> float | None:
    matches = list(AMOUNT_RE.finditer(text))
    if not matches:
        return None
    raw = matches[-1].group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _detect_category(text: str) -> str:
    lower = text.lower()
    for key, cat in CATEGORY_MAP.items():
        if key in lower:
            return cat
    return "other"


def parse_quick_input(text: str) -> tuple[TransactionCreate, float, str]:
    """Return (transaction draft, confidence, explanation)."""
    clean = text.strip()
    lower = clean.lower()
    amount = _parse_amount(clean)
    if amount is None:
        raise ValueError("Не удалось найти сумму. Пример: «-1200 пятерочка» или «+50000 зарплата»")

    abs_amount = abs(amount)
    category = _detect_category(lower)
    tx_type = "expense"
    signed = -abs_amount
    explanation = "Распознан расход"

    if any(k in lower for k in DEBT_OWED) or "мне должен" in lower:
        tx_type = "debt"
        signed = abs_amount
        category = "debt_owed"
        explanation = "Долг вам (кто-то должен)"
    elif any(k in lower for k in DEBT_I_OWE):
        tx_type = "debt"
        signed = -abs_amount
        category = "debt_owing"
        explanation = "Ваш долг"
    elif any(k in lower for k in INVEST_KW):
        tx_type = "investment"
        signed = -abs_amount
        category = "investments"
        explanation = "Инвестиция"
    elif any(k in lower for k in SAVINGS_KW):
        tx_type = "savings"
        signed = -abs_amount
        category = "savings"
        explanation = "Пополнение накоплений"
    elif amount > 0 or any(k in lower for k in INCOME_KEYWORDS):
        tx_type = "income"
        signed = abs_amount
        category = category if category != "other" else "salary"
        explanation = "Доход"
    elif amount < 0 or any(k in lower for k in EXPENSE_KEYWORDS):
        tx_type = "expense"
        signed = -abs_amount
        explanation = "Расход"

    # merchant / description heuristic
    desc = re.sub(AMOUNT_RE, "", clean).strip(" -+,.")
    merchant = desc[:200] if desc else category

    confidence = 0.72
    if any(k in lower for k in CATEGORY_MAP):
        confidence += 0.12
    if clean.startswith(("+", "-")):
        confidence += 0.08
    confidence = min(confidence, 0.98)

    draft = TransactionCreate(
        amount=signed,
        category=category,
        description=desc or explanation,
        merchant=merchant,
        transaction_type=tx_type,
        occurred_on=date.today(),
        source="quick_input",
        raw_input=clean,
        tags="quick",
    )
    return draft, confidence, explanation
