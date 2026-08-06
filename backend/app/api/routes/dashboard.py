from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.build_dashboard(db)


@router.get("/ritual/morning")
async def morning(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.morning_ritual(db)


@router.get("/ritual/evening")
async def evening(db: AsyncSession = Depends(get_db)):
    return await dashboard_service.evening_ritual(db)
