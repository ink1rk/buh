from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _unicode_case(connection, _record):
    """Научить SQLite строчным буквам кириллицы.

    Встроенные `lower`/`upper` меняют регистр только латиницы, а на них стоит
    поиск без учёта регистра: «Бензин» не находился по запросу «бензин».
    Приложению на русском такой поиск бесполезен. Слушатель общий, а не на
    одном движке: своё соединение заводят и тесты.
    """
    if not hasattr(connection, "create_function"):
        return
    connection.create_function("lower", 1, lambda s: s.lower() if s else s,
                               deterministic=True)
    connection.create_function("upper", 1, lambda s: s.upper() if s else s,
                               deterministic=True)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
