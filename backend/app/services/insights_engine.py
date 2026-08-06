"""Daily AI insights from transaction patterns."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from app.models.subscription import Subscription
from app.models.transaction import Transaction


def generate_insights(
    transactions: list[Transaction],
    subscriptions: list[Subscription],
    monthly_income: float,
) -> list[dict]:
    today = date.today()
    month_start = today.replace(day=1)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    this_month = [t for t in transactions if t.occurred_on >= month_start and t.amount < 0]
    prev_month = [
        t for t in transactions if prev_start <= t.occurred_on < month_start and t.amount < 0
    ]

    insights: list[dict] = []

    # Category growth
    def cat_sum(rows: list[Transaction]) -> dict[str, float]:
        d: dict[str, float] = defaultdict(float)
        for t in rows:
            d[t.category] += abs(t.amount)
        return d

    cur = cat_sum(this_month)
    prev = cat_sum(prev_month)
    for cat, val in cur.items():
        if prev.get(cat, 0) > 0:
            growth = (val - prev[cat]) / prev[cat] * 100
            if growth >= 30:
                insights.append(
                    {
                        "title": f"Рост «{cat}» на {growth:.0f}%",
                        "body": f"В этом месяце категория «{cat}» выросла до {val:,.0f} ₽.".replace(",", " "),
                        "insight_type": "warning",
                        "severity": "warning",
                        "category": cat,
                    }
                )

    # Coffee frequency
    coffee = [t for t in this_month if t.category == "cafe" or "кофе" in (t.description or "").lower()]
    if len(coffee) >= 8:
        insights.append(
            {
                "title": "Ты стал чаще покупать кофе",
                "body": f"Уже {len(coffee)} покупок кофе/кафе за месяц на {sum(abs(t.amount) for t in coffee):,.0f} ₽.".replace(",", " "),
                "insight_type": "pattern",
                "severity": "info",
                "category": "cafe",
            }
        )

    # Spending down praise
    week = [t for t in this_month if t.occurred_on >= today - timedelta(days=21)]
    if week:
        w1 = sum(abs(t.amount) for t in week if t.occurred_on >= today - timedelta(days=7))
        w3 = sum(abs(t.amount) for t in week if today - timedelta(days=21) <= t.occurred_on < today - timedelta(days=14))
        if w3 > 0 and w1 < w3 * 0.85:
            insights.append(
                {
                    "title": "Последние недели тратишь меньше",
                    "body": "Отличная динамика. Зафиксируй разницу как перевод в инвестиции.",
                    "insight_type": "praise",
                    "severity": "success",
                    "category": "discipline",
                }
            )

    # Subscriptions share
    subs_total = sum(s.amount for s in subscriptions if s.is_active)
    if monthly_income > 0 and subs_total / monthly_income >= 0.05:
        insights.append(
            {
                "title": f"Подписки съедают {subs_total / monthly_income * 100:.0f}% дохода",
                "body": f"≈ {subs_total:,.0f} ₽/мес. Проверьте неиспользуемые сервисы.".replace(",", " "),
                "insight_type": "alert",
                "severity": "warning",
                "category": "subscriptions",
            }
        )

    # Unused subscriptions
    for s in subscriptions:
        if not s.is_active or not s.last_used_date:
            continue
        unused = (today - s.last_used_date).days
        if unused >= s.unused_days_threshold:
            insights.append(
                {
                    "title": f"«{s.name}» без использования {unused} дн.",
                    "body": f"Подписка за {s.amount:,.0f} ₽. Отключить?".replace(",", " "),
                    "insight_type": "opportunity",
                    "severity": "info",
                    "category": "subscriptions",
                }
            )

    # Delivery vs phone heuristic
    delivery = sum(abs(t.amount) for t in this_month if "достав" in (t.description or "").lower() or t.category == "restaurants")
    if delivery >= 40000:
        insights.append(
            {
                "title": "Доставка ≈ стоимость нового телефона",
                "body": f"Рестораны/доставка уже {delivery:,.0f} ₽ за месяц.".replace(",", " "),
                "insight_type": "pattern",
                "severity": "warning",
                "category": "restaurants",
            }
        )

    # Invest opportunity
    income_like = sum(t.amount for t in transactions if t.occurred_on >= month_start and t.amount > 0)
    expense = sum(abs(t.amount) for t in this_month)
    if income_like - expense > monthly_income * 0.2:
        insights.append(
            {
                "title": "Хороший момент увеличить инвестиции",
                "body": "Свободный остаток выше обычного. Переведите часть в портфель сегодня.",
                "insight_type": "opportunity",
                "severity": "success",
                "category": "investments",
            }
        )

    if not insights:
        insights.append(
            {
                "title": "Стабильный день",
                "body": "Явных аномалий нет. Отличный момент усилить главную цель небольшим взносом.",
                "insight_type": "praise",
                "severity": "info",
                "category": "general",
            }
        )

    return insights[:8]
