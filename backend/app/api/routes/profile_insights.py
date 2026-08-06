"""Habits, risk radar, and happiness index — the user's behavioral profile."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calendar import CalendarEvent
from app.models.debt import Debt
from app.models.happiness import PurchaseRating
from app.models.transaction import Transaction
from app.schemas.happiness import FollowUpRating, HappinessInsight, PurchaseRatingCreate, PurchaseRatingOut
from app.services.dashboard_service import compute_balances, get_or_create_profile
from app.services.habits_engine import compute_habits
from app.services.happiness_engine import build_category_insights, create_rating, pending_followups, submit_followup
from app.services.risk_engine import compute_risks

router = APIRouter(tags=["profile"])


@router.get("/habits")
async def habits(db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    txs = list((await db.execute(select(Transaction))).scalars())
    return compute_habits(txs, profile.monthly_income)


@router.get("/risks")
async def risks(db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    balances = await compute_balances(db)
    debts = list((await db.execute(select(Debt).where(Debt.is_active.is_(True)))).scalars())
    total_debt = sum(d.remaining for d in debts if d.direction == "i_owe")
    events = list((await db.execute(select(CalendarEvent))).scalars())
    income_sources = 1 if profile.monthly_income > 0 else 0
    txs = list((await db.execute(select(Transaction).where(Transaction.transaction_type == "income"))).scalars())
    distinct_merchants = {t.merchant for t in txs if t.merchant}
    income_sources = max(income_sources, min(len(distinct_merchants), 3))
    return compute_risks(
        monthly_income=profile.monthly_income or balances.income_month,
        monthly_expense=balances.expense_month,
        reserve=balances.reserve + balances.savings,
        total_debt=total_debt,
        income_sources=income_sources,
        upcoming_events=events,
        liquid_balance=balances.total,
    )


@router.post("/happiness/rate", response_model=PurchaseRatingOut)
async def rate_purchase(payload: PurchaseRatingCreate, db: AsyncSession = Depends(get_db)):
    row = await create_rating(
        db, payload.item, payload.price, payload.category, payload.initial_rating, payload.transaction_id
    )
    return row


@router.get("/happiness/pending", response_model=list[PurchaseRatingOut])
async def get_pending(db: AsyncSession = Depends(get_db)):
    return await pending_followups(db)


@router.post("/happiness/{rating_id}/followup", response_model=PurchaseRatingOut)
async def followup(rating_id: int, payload: FollowUpRating, db: AsyncSession = Depends(get_db)):
    row = await submit_followup(db, rating_id, payload.rating)
    return row


@router.get("/happiness/insights", response_model=list[HappinessInsight])
async def happiness_insights(db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(select(PurchaseRating))).scalars())
    return build_category_insights(rows)
