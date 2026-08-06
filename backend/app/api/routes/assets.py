from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.capital import Asset
from app.schemas.capital import AssetCreate, AssetOut

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetOut])
async def list_assets(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Asset))).scalars()
    return list(rows)


@router.post("", response_model=AssetOut)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)):
    row = Asset(**payload.model_dump())
    db.add(row)
    await db.flush()
    return row
