from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


def enrich(goal: Goal) -> GoalOut:
    remaining = max(goal.target_amount - goal.current_amount, 0)
    progress = goal.current_amount / max(goal.target_amount, 1) * 100
    months_left = None
    if goal.monthly_contribution > 0 and remaining > 0:
        months_left = round(remaining / goal.monthly_contribution, 1)
    # refresh probability heuristic
    if goal.deadline and goal.monthly_contribution > 0:
        months_to_deadline = max(
            (goal.deadline.year - date.today().year) * 12 + goal.deadline.month - date.today().month,
            1,
        )
        needed = remaining / months_to_deadline
        goal.probability = min(0.98, max(0.15, goal.monthly_contribution / max(needed, 1) * 0.7))
    return GoalOut(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        monthly_contribution=goal.monthly_contribution,
        deadline=goal.deadline,
        icon=goal.icon,
        color=goal.color,
        category=goal.category,
        priority=goal.priority,
        is_active=goal.is_active,
        probability=round(goal.probability, 2),
        remaining=round(remaining, 2),
        progress_pct=round(progress, 1),
        months_left=months_left,
    )


@router.get("", response_model=list[GoalOut])
async def list_goals(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Goal).order_by(Goal.priority, Goal.id))).scalars()
    return [enrich(g) for g in rows]


@router.post("", response_model=GoalOut)
async def create_goal(payload: GoalCreate, db: AsyncSession = Depends(get_db)):
    row = Goal(**payload.model_dump())
    db.add(row)
    await db.flush()
    return enrich(row)


@router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(goal_id: int, payload: GoalUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Goal, goal_id)
    if not row:
        raise HTTPException(404, "Goal not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return enrich(row)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(goal_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Goal, goal_id)
    if not row:
        raise HTTPException(404, "Goal not found")
    await db.delete(row)
    await db.flush()
    return Response(status_code=204)
