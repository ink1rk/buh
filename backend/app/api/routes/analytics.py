from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.analytics import ScenarioRequest
from app.services.analytics_engine import build_analytics
from app.services.dashboard_service import compute_balances, get_or_create_profile
from app.services.forecast_engine import build_forecast, run_scenario
from app.services.review_engine import build_review

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/bundle")
async def analytics_bundle(days: int = Query(90, ge=7, le=365), db: AsyncSession = Depends(get_db)):
    txs = list((await db.execute(select(Transaction))).scalars())
    accounts = list((await db.execute(select(Account))).scalars())
    return build_analytics(txs, accounts, days=days)


@router.get("/review")
async def statement_review(db: AsyncSession = Depends(get_db)):
    """Средние по полным месяцам выписки и советы с цифрами."""
    txs = list((await db.execute(select(Transaction))).scalars())
    return build_review(txs)


@router.get("/forecast")
async def forecast(db: AsyncSession = Depends(get_db)):
    balances = await compute_balances(db)
    profile = await get_or_create_profile(db)
    txs = list((await db.execute(select(Transaction))).scalars())
    review = build_review(txs)
    # Обрывок текущего месяца прогнозом не является: берём средние полных.
    income = review.earned_month if review.ready else (
        profile.monthly_income or balances.income_month
    )
    expense = review.spent_month if review.ready else (
        balances.expense_month or profile.monthly_income * 0.6
    )
    return build_forecast(
        balances.total,
        income,
        expense,
        monthly_invest=balances.investments * 0.02,
    )


@router.post("/scenarios")
async def scenarios(payload: ScenarioRequest, db: AsyncSession = Depends(get_db)):
    balances = await compute_balances(db)
    profile = await get_or_create_profile(db)
    return run_scenario(
        payload,
        balances.total,
        profile.monthly_income or balances.income_month,
        balances.expense_month or 100000,
    )


@router.get("/cashflow")
async def cashflow(db: AsyncSession = Depends(get_db)):
    bundle = await analytics_bundle(90, db)
    return bundle.cashflow
