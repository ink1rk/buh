from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.achievement import Achievement, UserAchievement
from app.models.transaction import Transaction
from app.services.timeline_service import build_timeline

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("")
async def get_timeline(db: AsyncSession = Depends(get_db)):
    txs = list((await db.execute(select(Transaction))).scalars())
    ua_rows = list((await db.execute(select(UserAchievement))).scalars())
    ach_map = {a.id: a for a in (await db.execute(select(Achievement))).scalars()}
    unlocked = [(ach_map[u.achievement_id], u) for u in ua_rows if u.achievement_id in ach_map]
    return build_timeline(txs, unlocked)
