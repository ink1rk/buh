"""Начать с чистого листа.

Показательный набор данных нужен, чтобы пустое приложение не выглядело
сломанным. Но как только приходят настоящие деньги, выдуманные обязаны уйти:
иначе капитал складывается из несуществующих счетов, а «расходы за месяц» —
наполовину из чужой жизни. Пока они лежат вперемешку, отличить одно от
другого нельзя ни на глаз, ни в расчётах.

Подключения к банкам владелец заводил сам — их и историю загрузок оставляем,
чтобы выписку можно было залить заново, а вот разобранные операции стираем
вместе с транзакциями: иначе повторная загрузка того же файла уйдёт в дубли.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.budget import BudgetEnvelope
from app.models.achievement import UserAchievement
from app.models.calendar import CalendarEvent
from app.models.capital import Asset, NetWorthSnapshot
from app.models.coach import DailyChallenge
from app.models.connection import BankConnection, BankImport, BankOperation
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.happiness import PurchaseRating
from app.models.insight import Insight
from app.models.investment import InvestmentHolding
from app.models.memory import AIMemory
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user import UserProfile
from app.models.widget import DailyWidget

# Справочник достижений (`achievements`) — не данные владельца, а список того,
# что вообще бывает; он переживает очистку.
WIPED = [
    ("операции", Transaction),
    ("счета", Account),
    ("цели", Goal),
    ("бюджет", BudgetEnvelope),
    ("долги", Debt),
    ("подписки", Subscription),
    ("имущество", Asset),
    ("вложения", InvestmentHolding),
    ("снимки капитала", NetWorthSnapshot),
    ("события календаря", CalendarEvent),
    ("заметки ИИ", AIMemory),
    ("наблюдения", Insight),
    ("оценки покупок", PurchaseRating),
    ("полученные достижения", UserAchievement),
    ("виджеты дня", DailyWidget),
    ("задачи коуча", DailyChallenge),
    ("операции банка", BankOperation),
    ("загрузки выписок", BankImport),
]


async def clean_slate(db: AsyncSession) -> dict:
    """Стереть все финансовые данные, оставив подключения и сам профиль."""
    removed = {}
    for label, model in WIPED:
        count = await db.scalar(select(func.count()).select_from(model)) or 0
        if count:
            removed[label] = count
        await db.execute(delete(model))

    # Подключения остаются, но их счётчики говорили бы о стёртом.
    await db.execute(update(BankConnection).values(
        account_id=None, imported_total=0, last_operation_on=None,
        last_synced_at=None, last_error="", status="idle"))

    profile = (await db.execute(select(UserProfile))).scalars().first()
    if profile is not None:
        # Имя и валюта — про человека, остальное было про выдуманного.
        profile.monthly_income = 0
        profile.dreams = ""
        profile.fears = ""
        profile.habits_notes = ""
        profile.onboarding_done = False

    await db.flush()
    return {"removed": removed, "total": sum(removed.values())}
