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


def _ensure_calendar_ingest_columns(sync_conn):
    """create_all не добавляет колонки в уже существующую таблицу."""
    rows = sync_conn.exec_driver_sql("PRAGMA table_info(calendar_events)").fetchall()
    names = {row[1] for row in rows}
    if "external_id" not in names:
        sync_conn.exec_driver_sql(
            "ALTER TABLE calendar_events ADD COLUMN external_id VARCHAR(200) DEFAULT ''"
        )
    if "source" not in names:
        sync_conn.exec_driver_sql(
            "ALTER TABLE calendar_events ADD COLUMN source VARCHAR(32) DEFAULT ''"
        )


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_calendar_ingest_columns)
        await conn.run_sync(_reclassify_known_merchants)


def _reclassify_known_merchants(sync_conn):
    """Касса «VV_…» и похожие места больше не висят в «прочем»."""
    from app.services.review_engine import reclassify_unclear

    reclassify_unclear(sync_conn)
