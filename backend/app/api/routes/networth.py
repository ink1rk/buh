from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.net_worth_service import build_contribution_graph, build_net_worth, compute_capital_map

router = APIRouter(prefix="/networth", tags=["networth"])


@router.get("")
async def net_worth(db: AsyncSession = Depends(get_db)):
    return await build_net_worth(db)


@router.get("/capital-map")
async def capital_map(db: AsyncSession = Depends(get_db)):
    return await compute_capital_map(db)


@router.get("/contribution-graph")
async def contribution_graph(days: int = Query(365, ge=30, le=730), db: AsyncSession = Depends(get_db)):
    return await build_contribution_graph(db, days=days)
