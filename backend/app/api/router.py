from fastapi import APIRouter

from app.api.routes import accounts, ai, analytics, dashboard, goals, misc, transactions

api_router = APIRouter()
api_router.include_router(dashboard.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(goals.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(misc.router)
