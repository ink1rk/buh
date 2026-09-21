from fastapi import APIRouter

from app.api.routes import (
    accounts,
    ai,
    analytics,
    assets,
    coach,
    connections,
    dashboard,
    goals,
    misc,
    networth,
    profile_insights,
    timeline,
    transactions,
)

api_router = APIRouter()
api_router.include_router(dashboard.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(goals.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(misc.router)
api_router.include_router(networth.router)
api_router.include_router(assets.router)
api_router.include_router(timeline.router)
api_router.include_router(profile_insights.router)
api_router.include_router(coach.router)
api_router.include_router(connections.router)
