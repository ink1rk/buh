from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

DbSession = AsyncGenerator[AsyncSession, None]

__all__ = ["get_db", "DbSession"]
