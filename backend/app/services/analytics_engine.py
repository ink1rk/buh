"""Analytics aggregations for charts (Plotly-ready payloads)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.analytics import (
    AnalyticsBundle,
    CashFlowDiagram,
    CashFlowLink,
    CashFlowNode,
    CategorySlice,
    HeatmapCell,
    TimeSeriesPoint,
)

CATEGORY_COLORS = {
    "groceries": "#34d399",
    "cafe": "#fbbf24",
    "restaurants": "#f87171",
    "transport": "#60a5fa",
    "housing": "#a78bfa",
    "subscriptions": "#c084fc",
    "health": "#2dd4bf",
    "gadgets": "#818cf8",
    "salary": "#4ade80",
    "investments": "#38bdf8",
    "savings": "#fbbf24",
    "other": "#94a3b8",
}


def build_analytics(
    transactions: list[Transaction],
    accounts: list[Account],
    days: int = 90,
) -> AnalyticsBundle:
    today = date.today()
    start = today - timedelta(days=days - 1)

    by_day: dict[date, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    by_cat: dict[str, float] = defaultdict(float)

    for tx in transactions:
        if tx.occurred_on < start:
            continue
        if tx.amount >= 0 and tx.transaction_type == "income":
            by_day[tx.occurred_on]["income"] += tx.amount
        elif tx.amount < 0:
            by_day[tx.occurred_on]["expense"] += abs(tx.amount)
            by_cat[tx.category or "other"] += abs(tx.amount)

    timeseries: list[TimeSeriesPoint] = []
    for i in range(days):
        d = start + timedelta(days=i)
        inc = by_day[d]["income"]
        exp = by_day[d]["expense"]
        timeseries.append(TimeSeriesPoint(date=d.isoformat(), income=inc, expense=exp, net=inc - exp))

    by_category = [
        CategorySlice(name=k, value=round(v, 2), color=CATEGORY_COLORS.get(k, "#94a3b8"))
        for k, v in sorted(by_cat.items(), key=lambda x: -x[1])
    ]

    heatmap: list[HeatmapCell] = []
    for i in range(days):
        d = start + timedelta(days=i)
        heatmap.append(
            HeatmapCell(
                date=d.isoformat(),
                value=round(by_day[d]["expense"], 2),
                weekday=d.weekday(),
                week=d.isocalendar()[1],
            )
        )

    income_month = sum(t.income for t in timeseries[-30:])
    expense_month = sum(t.expense for t in timeseries[-30:])
    invest = sum(a.balance for a in accounts if a.account_type == "investment")
    savings = sum(a.balance for a in accounts if a.account_type in ("savings", "reserve"))
    free = max(income_month - expense_month - invest * 0.05, 0)

    cashflow = CashFlowDiagram(
        nodes=[
            CashFlowNode("income", "Доход", round(income_month, 2), "#4ade80"),
            CashFlowNode("distribute", "Распределение", round(income_month, 2), "#60a5fa"),
            CashFlowNode("expense", "Расходы", round(expense_month, 2), "#f87171"),
            CashFlowNode("invest", "Инвестиции", round(invest * 0.05, 2), "#38bdf8"),
            CashFlowNode("savings", "Накопления", round(min(savings * 0.1, free * 0.4), 2), "#fbbf24"),
            CashFlowNode("free", "Свободный остаток", round(free, 2), "#a78bfa"),
        ],
        links=[
            CashFlowLink("income", "distribute", round(income_month, 2)),
            CashFlowLink("distribute", "expense", round(expense_month, 2)),
            CashFlowLink("distribute", "invest", round(invest * 0.05, 2)),
            CashFlowLink("distribute", "savings", round(min(savings * 0.1, free * 0.4), 2)),
            CashFlowLink("distribute", "free", round(free, 2)),
        ],
    )

    radar = [
        {"axis": "Сбережения", "value": min(100, savings / max(income_month, 1) * 50)},
        {"axis": "Инвестиции", "value": min(100, invest / max(income_month * 6, 1) * 100)},
        {"axis": "Контроль", "value": max(0, 100 - expense_month / max(income_month, 1) * 100)},
        {"axis": "Подушка", "value": min(100, savings / max(expense_month * 3, 1) * 100)},
        {"axis": "Рост", "value": min(100, (income_month - expense_month) / max(income_month, 1) * 200)},
        {"axis": "Дисциплина", "value": min(100, len(transactions) / 30 * 40)},
    ]

    waterfall = [
        {"name": "Доход", "value": round(income_month, 2), "measure": "absolute"},
        {"name": "Расходы", "value": -round(expense_month, 2), "measure": "relative"},
        {"name": "Инвестиции", "value": -round(invest * 0.05, 2), "measure": "relative"},
        {"name": "Итог", "value": round(income_month - expense_month, 2), "measure": "total"},
    ]

    return AnalyticsBundle(
        timeseries=timeseries,
        by_category=by_category,
        heatmap=heatmap,
        cashflow=cashflow,
        radar=radar,
        waterfall=waterfall,
        treemap=by_category,
    )
