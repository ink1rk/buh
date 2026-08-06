from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.coach import DailyChallenge
from app.schemas.coach import DailyChallengeOut
from app.services.coach_engine import ensure_today_challenge

router = APIRouter(prefix="/coach", tags=["coach"])


@router.get("/today", response_model=DailyChallengeOut)
async def today_challenge(db: AsyncSession = Depends(get_db)):
    return await ensure_today_challenge(db)


@router.post("/{challenge_id}/complete", response_model=DailyChallengeOut)
async def complete_challenge(challenge_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DailyChallenge, challenge_id)
    if not row:
        raise HTTPException(404, "Challenge not found")
    row.is_completed = True
    await db.flush()
    return row
