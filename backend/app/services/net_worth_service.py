"""Net Worth engine — the single most important number in the app.

Tracks daily snapshots so the user sees the number move every day
(today / month / year deltas), and builds the "capital map":
money, real estate, car, investments, crypto, gold, tech, debts, net capital.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.capital import Asset, NetWorthSnapshot
from app.models.debt import Debt
from app.models.transaction import Transaction
from app.schemas.capital import (
    AssetOut,
    CapitalMap,
    CapitalSlice,
    ContributionDay,
    NetWorthDelta,
    NetWorthOut,
    NetWorthPoint,
)

ASSET_TYPE_COLORS = {
    "real_estate": "#a78bfa",
    "car": "#60a5fa",
    "gold": "#fbbf24",
    "tech": "#818cf8",
    "other": "#94a3b8",
}


async def _totals(db: AsyncSession) -> dict[str, float]:
    accounts = list((await db.execute(select(Account).where(Account.is_active.is_(True)))).scalars())
    assets = list((await db.execute(select(Asset))).scalars())
    debts = list((await db.execute(select(Debt).where(Debt.is_active.is_(True)))).scalars())

    money = sum(a.balance for a in accounts if a.account_type in ("cash", "card", "bank", "savings", "reserve"))
    investments = sum(a.balance for a in accounts if a.account_type == "investment")
    crypto = sum(a.balance for a in accounts if a.account_type == "crypto")
    real_estate = sum(a.value for a in assets if a.asset_type == "real_estate")
    car = sum(a.value for a in assets if a.asset_type == "car")
    gold = sum(a.value for a in assets if a.asset_type == "gold")
    tech = sum(a.value for a in assets if a.asset_type == "tech")
    other_assets = sum(a.value for a in assets if a.asset_type == "other")

    owed_to_me = sum(d.remaining for d in debts if d.direction == "owed_to_me")
    i_owe = sum(d.remaining for d in debts if d.direction == "i_owe")

    total_capital = money + investments + crypto + real_estate + car + gold + tech + other_assets + owed_to_me
    net_capital = total_capital - i_owe

    return {
        "money": money,
        "investments": investments,
        "crypto": crypto,
        "real_estate": real_estate,
        "car": car,
        "gold": gold,
        "tech": tech,
        "other_assets": other_assets,
        "owed_to_me": owed_to_me,
        "i_owe": i_owe,
        "total_capital": total_capital,
        "net_capital": net_capital,
    }


async def compute_capital_map(db: AsyncSession) -> CapitalMap:
    t = await _totals(db)
    assets = list((await db.execute(select(Asset))).scalars())
    slices = [
        CapitalSlice(key="money", label="Деньги", value=round(t["money"], 2), color="#34d399"),
        CapitalSlice(key="investments", label="Инвестиции", value=round(t["investments"], 2), color="#38bdf8"),
        CapitalSlice(key="crypto", label="Крипта", value=round(t["crypto"], 2), color="#c084fc"),
        CapitalSlice(key="real_estate", label="Недвижимость", value=round(t["real_estate"], 2), color="#a78bfa"),
        CapitalSlice(key="car", label="Автомобиль", value=round(t["car"], 2), color="#60a5fa"),
        CapitalSlice(key="gold", label="Золото", value=round(t["gold"], 2), color="#fbbf24"),
        CapitalSlice(key="tech", label="Техника", value=round(t["tech"], 2), color="#818cf8"),
        CapitalSlice(key="owed_to_me", label="Мне должны", value=round(t["owed_to_me"], 2), color="#5eead4"),
    ]
    slices = [s for s in slices if s.value > 0]
    return CapitalMap(
        total_capital=round(t["total_capital"], 2),
        net_capital=round(t["net_capital"], 2),
        slices=slices,
        total_debts=round(t["i_owe"], 2),
        assets=[AssetOut.model_validate(a) for a in assets],
    )


def _rate_day(net: float, expense: float, income: float) -> str:
    if net > 0:
        return "good"
    if expense > 0 and income == 0 and expense > (income or 1) * 1.3:
        return "overspend"
    if net < -500:
        return "overspend"
    return "neutral"


async def ensure_daily_snapshot(db: AsyncSession) -> NetWorthSnapshot:
    today = date.today()
    existing = (
        await db.execute(select(NetWorthSnapshot).where(NetWorthSnapshot.snapshot_date == today))
    ).scalar_one_or_none()

    t = await _totals(db)
    txs_today = list(
        (await db.execute(select(Transaction).where(Transaction.occurred_on == today))).scalars()
    )
    day_income = sum(tx.amount for tx in txs_today if tx.amount > 0)
    day_expense = sum(abs(tx.amount) for tx in txs_today if tx.amount < 0)
    rating = _rate_day(day_income - day_expense, day_expense, day_income)

    if existing:
        existing.net_worth = t["net_capital"]
        existing.total_liquid = t["money"]
        existing.total_assets = t["real_estate"] + t["car"] + t["gold"] + t["tech"] + t["other_assets"]
        existing.total_investments = t["investments"] + t["crypto"]
        existing.total_debts = t["i_owe"]
        existing.day_income = day_income
        existing.day_expense = day_expense
        existing.day_rating = rating
        await db.flush()
        return existing

    row = NetWorthSnapshot(
        snapshot_date=today,
        net_worth=t["net_capital"],
        total_liquid=t["money"],
        total_assets=t["real_estate"] + t["car"] + t["gold"] + t["tech"] + t["other_assets"],
        total_investments=t["investments"] + t["crypto"],
        total_debts=t["i_owe"],
        day_income=day_income,
        day_expense=day_expense,
        day_rating=rating,
    )
    db.add(row)
    await db.flush()
    return row


async def build_net_worth(db: AsyncSession) -> NetWorthOut:
    today_snap = await ensure_daily_snapshot(db)
    history = list(
        (
            await db.execute(
                select(NetWorthSnapshot)
                .where(NetWorthSnapshot.snapshot_date >= date.today() - timedelta(days=365))
                .order_by(NetWorthSnapshot.snapshot_date)
            )
        ).scalars()
    )

    def _closest(days_back: int) -> float:
        target = date.today() - timedelta(days=days_back)
        candidates = [h for h in history if h.snapshot_date <= target]
        return candidates[-1].net_worth if candidates else (history[0].net_worth if history else today_snap.net_worth)

    delta = NetWorthDelta(
        today=round(today_snap.net_worth - _closest(1), 2),
        month=round(today_snap.net_worth - _closest(30), 2),
        year=round(today_snap.net_worth - _closest(365), 2),
    )

    capital_map = await compute_capital_map(db)

    return NetWorthOut(
        current=round(today_snap.net_worth, 2),
        delta=delta,
        history=[
            NetWorthPoint(date=h.snapshot_date.isoformat(), net_worth=h.net_worth, rating=h.day_rating)
            for h in history
        ],
        capital_map=capital_map,
    )


async def build_contribution_graph(db: AsyncSession, days: int = 365) -> list[ContributionDay]:
    history = {
        h.snapshot_date: h
        for h in (
            await db.execute(
                select(NetWorthSnapshot).where(
                    NetWorthSnapshot.snapshot_date >= date.today() - timedelta(days=days)
                )
            )
        ).scalars()
    }
    out: list[ContributionDay] = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        snap = history.get(d)
        if snap:
            out.append(
                ContributionDay(
                    date=d.isoformat(),
                    rating=snap.day_rating,
                    net=round(snap.day_income - snap.day_expense, 2),
                )
            )
        else:
            out.append(ContributionDay(date=d.isoformat(), rating="empty", net=0))
    return out
