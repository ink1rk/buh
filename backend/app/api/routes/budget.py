from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.budget import BudgetPlan, BudgetPut
from app.services.budget_service import build_plan, replace_plan, seed_from_history
from app.services.dashboard_service import get_or_create_profile

router = APIRouter(prefix="/budget", tags=["budget"])


@router.get("", response_model=BudgetPlan)
async def get_budget(db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    return await build_plan(db, profile)


@router.put("", response_model=BudgetPlan)
async def put_budget(payload: BudgetPut, db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    return await replace_plan(db, profile, payload.envelopes, payload.monthly_income)


@router.post("/seed", response_model=BudgetPlan)
async def seed_budget(replace: bool = False, db: AsyncSession = Depends(get_db)):
    """Собрать конверты из среднего за год выписки.

    По умолчанию не трогает уже сохранённый план: случайный повтор не
    затирает правки. replace=true — пересчитать заново.
    """
    profile = await get_or_create_profile(db)
    return await seed_from_history(db, profile, replace=replace)
