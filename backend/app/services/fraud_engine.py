"""Lightweight anomaly detection: flags transactions unlike the user's habits."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev

from app.models.transaction import Transaction
from app.schemas.ai import FraudAlert


def detect_anomalies(transactions: list[Transaction], lookback_days: int = 120) -> list[FraudAlert]:
    today = date.today()
    cutoff = today - timedelta(days=lookback_days)
    history = [t for t in transactions if t.occurred_on >= cutoff and t.amount < 0]
    recent = [t for t in history if t.occurred_on >= today - timedelta(days=3)]

    known_merchants = {t.merchant.lower() for t in history if t.merchant}
    by_category: dict[str, list[float]] = defaultdict(list)
    for t in history:
        by_category[t.category].append(abs(t.amount))

    alerts: list[FraudAlert] = []
    for t in recent:
        reasons: list[str] = []
        amount = abs(t.amount)
        merchant = (t.merchant or "").lower()

        cat_values = by_category.get(t.category, [])
        if len(cat_values) >= 4:
            m = mean(cat_values)
            sd = pstdev(cat_values) or 1.0
            z = (amount - m) / sd
            if z >= 2.5:
                reasons.append(f"Сильно отличается от привычных трат в категории «{t.category}» (в {amount / max(m, 1):.1f}× больше обычного)")

        if merchant and merchant not in known_merchants - {merchant}:
            # first time seeing this merchant and it's a meaningfully large amount
            if amount >= max(mean(cat_values) if cat_values else 3000, 3000) * 1.5:
                reasons.append(f"Вы никогда раньше не покупали в «{t.merchant}»")

        if reasons:
            alerts.append(
                FraudAlert(
                    transaction_id=t.id,
                    title="Необычная операция",
                    reason=" · ".join(reasons),
                    severity="warning" if len(reasons) == 1 else "high",
                    amount=amount,
                    merchant=t.merchant or t.category,
                )
            )

    return alerts[:5]
