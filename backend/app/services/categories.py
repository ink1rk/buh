"""Названия категорий по-русски.

В базе категория — это код: `health`, `groceries`, `transfers`. Так удобно
сравнивать и группировать, но в тексте подсказки код выглядит как чужое слово:
«Рост «health» на 200%» в остальном русском интерфейсе. Словарь один на все
подсказки, чтобы одна и та же категория не называлась в двух местах по-разному.

Тот же список повторён во фронтенде (`src/lib/categories.ts`): там он ещё и
раскрашивает графики. Добавляя категорию, добавляйте в оба.
"""

from __future__ import annotations

CATEGORY_NAMES: dict[str, str] = {
    "groceries": "продукты",
    "cafe": "кофе и перекусы",
    "restaurants": "кафе и рестораны",
    "transport": "транспорт",
    "travel": "путешествия",
    "housing": "жильё",
    "home": "дом и ремонт",
    "utilities": "ЖКХ и связь",
    "health": "здоровье",
    "beauty": "красота",
    "clothes": "одежда",
    "gadgets": "техника",
    "shopping": "покупки",
    "entertainment": "развлечения",
    "subscriptions": "подписки",
    "education": "образование",
    "kids": "дети",
    "pets": "питомцы",
    "services": "услуги",
    "taxes": "налоги и штрафы",
    "insurance": "страхование",
    "fees": "комиссии банка",
    "cash": "наличные",
    "transfers": "переводы",
    "savings": "накопления",
    "investments": "инвестиции",
    "salary": "зарплата",
    "cashback": "кэшбэк",
    "interest": "проценты по счёту",
    "refunds": "возвраты",
    "debt_owed": "долги мне",
    "debt_owing": "мои долги",
    "other": "прочие расходы",
    "other_income": "прочие поступления",
}


CATEGORY_COLORS: dict[str, str] = {
    "groceries": "#34d399",
    "cafe": "#fbbf24",
    "restaurants": "#f87171",
    "transport": "#60a5fa",
    "travel": "#22d3ee",
    "housing": "#a78bfa",
    "home": "#a78bfa",
    "utilities": "#7dd3fc",
    "health": "#2dd4bf",
    "beauty": "#f0abfc",
    "clothes": "#fb7185",
    "gadgets": "#818cf8",
    "shopping": "#f59e0b",
    "entertainment": "#e879f9",
    "subscriptions": "#c084fc",
    "education": "#a3e635",
    "kids": "#fda4af",
    "pets": "#facc15",
    "services": "#cbd5f5",
    "taxes": "#94a3b8",
    "insurance": "#64748b",
    "fees": "#9ca3af",
    "cash": "#fcd34d",
    "transfers": "#93c5fd",
    "savings": "#fbbf24",
    "investments": "#38bdf8",
    "salary": "#4ade80",
    "cashback": "#86efac",
    "interest": "#5eead4",
    "refunds": "#67e8f9",
    "other": "#94a3b8",
    "other_income": "#a7f3d0",
}

DEFAULT_COLOR = "#94a3b8"


def category_name(slug: str) -> str:
    """Категория словами. Незнакомый код лучше показать, чем потерять."""
    return CATEGORY_NAMES.get((slug or "").strip().lower(), slug or "без категории")


def category_color(slug: str) -> str:
    return CATEGORY_COLORS.get((slug or "").strip().lower(), DEFAULT_COLOR)
