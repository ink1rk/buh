"""AI Timeline — a GitHub-Activity-style feed of the user's financial life."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.achievement import Achievement, UserAchievement
from app.models.transaction import Transaction
from app.schemas.timeline import TimelineGroup, TimelineItem

TYPE_ICON = {
    "income": "trending-up",
    "expense": "shopping-bag",
    "investment": "line-chart",
    "savings": "piggy-bank",
    "debt": "handshake",
}
TYPE_COLOR = {
    "income": "#34d399",
    "expense": "#f87171",
    "investment": "#38bdf8",
    "savings": "#fbbf24",
    "debt": "#c084fc",
}


def _group_label(d: date, today: date) -> str:
    delta = (today - d).days
    if delta == 0:
        return "Сегодня"
    if delta == 1:
        return "Вчера"
    if delta <= 7:
        return "На этой неделе"
    if delta <= 14:
        return "Неделю назад"
    if delta <= 31:
        return "В этом месяце"
    return d.strftime("%B %Y")


def build_timeline(
    transactions: list[Transaction],
    unlocked: list[tuple[Achievement, UserAchievement]],
    limit_days: int = 45,
) -> list[TimelineGroup]:
    today = date.today()
    cutoff = today - timedelta(days=limit_days)

    by_date: dict[date, list[TimelineItem]] = {}

    for t in sorted(transactions, key=lambda x: x.occurred_on, reverse=True):
        if t.occurred_on < cutoff:
            continue
        icon = TYPE_ICON.get(t.transaction_type, "circle")
        color = TYPE_COLOR.get(t.transaction_type, "#94a3b8")
        label = t.description or t.merchant or t.category
        by_date.setdefault(t.occurred_on, []).append(
            TimelineItem(id=f"tx-{t.id}", icon=icon, title=label, amount=t.amount, color=color)
        )

    for ach, ua in unlocked:
        d = ua.unlocked_at.date() if hasattr(ua.unlocked_at, "date") else today
        if d < cutoff:
            continue
        by_date.setdefault(d, []).append(
            TimelineItem(id=f"ach-{ua.id}", icon="trophy", title=f"Достижение: {ach.title}", color="#fbbf24")
        )

    groups: list[TimelineGroup] = []
    for d in sorted(by_date.keys(), reverse=True):
        groups.append(TimelineGroup(label=_group_label(d, today), date=d.isoformat(), items=by_date[d]))

    return groups
