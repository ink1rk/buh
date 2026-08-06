"""Investment advisor — allocation, risk, rebalance (not a broker)."""

from __future__ import annotations

from app.models.investment import InvestmentHolding
from app.schemas.misc import PortfolioAdvice


def advise_portfolio(holdings: list[InvestmentHolding], emergency_months: float) -> PortfolioAdvice:
    total = sum(h.value for h in holdings) or 1.0
    by_class: dict[str, float] = {}
    for h in holdings:
        by_class[h.asset_class] = by_class.get(h.asset_class, 0) + h.value

    allocation = [
        {
            "asset_class": k,
            "value": round(v, 2),
            "pct": round(v / total * 100, 1),
        }
        for k, v in sorted(by_class.items(), key=lambda x: -x[1])
    ]

    risk = sum(h.risk_score * h.value for h in holdings) / total
    if risk < 0.3:
        risk_level = "Консервативный"
    elif risk < 0.55:
        risk_level = "Умеренный"
    else:
        risk_level = "Агрессивный"

    # diversification: number of classes + concentration penalty
    top_pct = max((a["pct"] for a in allocation), default=100)
    diversification = min(100.0, len(allocation) * 18 - max(0, top_pct - 50))

    suggestions: list[str] = []
    target = {"etf": 40, "bonds": 30, "cash": 15, "crypto": 10, "stocks": 5}
    for cls, tgt in target.items():
        cur = next((a["pct"] for a in allocation if a["asset_class"] == cls), 0)
        if abs(cur - tgt) >= 8:
            direction = "увеличить" if cur < tgt else "уменьшить"
            suggestions.append(f"{direction.capitalize()} долю {cls}: сейчас {cur}%, ориентир ~{tgt}%")

    if emergency_months < 3:
        suggestions.insert(0, "Сначала доведите подушку до 3–6 месяцев — затем рисковые активы.")

    return PortfolioAdvice(
        allocation=allocation,
        risk_level=risk_level,
        diversification_score=round(max(0, diversification), 1),
        rebalance_suggestions=suggestions[:5],
        emergency_fund_months=round(emergency_months, 1),
        inflation_note="Закладывайте инфляцию 6–10%: номинальная доходность ≠ реальная.",
        narrative=(
            f"Портфель {total:,.0f} ₽, риск — {risk_level.lower()}, "
            f"диверсификация {diversification:.0f}/100. "
            f"Подушка: {emergency_months:.1f} мес."
        ).replace(",", " "),
    )
