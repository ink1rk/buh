"""Pytest fixtures — isolated in-memory SQLite for every test."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import create_app
from app.models.account import Account
from app.models.capital import Asset
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user import UserProfile


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    Session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_db(db: AsyncSession) -> AsyncSession:
    """Minimal deterministic dataset for integration assertions."""
    db.add(UserProfile(name="Тест", monthly_income=200_000, onboarding_done=True))
    db.add_all(
        [
            Account(name="Карта", account_type="card", balance=100_000, sort_order=1),
            Account(name="Наличные", account_type="cash", balance=10_000, sort_order=2),
            Account(name="Брокер", account_type="investment", balance=200_000, sort_order=3),
            Account(name="Подушка", account_type="reserve", balance=150_000, sort_order=4),
            Account(name="Крипто", account_type="crypto", balance=50_000, sort_order=5),
        ]
    )
    db.add(Asset(name="Авто", asset_type="car", value=500_000, color="#60a5fa"))
    db.add(Debt(person_name="Саша", direction="i_owe", amount=5_000, remaining=5_000))
    db.add(Debt(person_name="Андрей", direction="owed_to_me", amount=12_000, remaining=12_000))
    db.add(
        Goal(
            title="Подушка",
            target_amount=300_000,
            current_amount=150_000,
            monthly_contribution=20_000,
            priority=1,
            probability=0.7,
        )
    )
    today = date.today()
    db.add_all(
        [
            Transaction(
                amount=200_000,
                category="salary",
                description="Зарплата",
                transaction_type="income",
                occurred_on=today.replace(day=min(10, today.day)),
                source="test",
            ),
            Transaction(
                amount=-3_000,
                category="groceries",
                description="Пятёрочка",
                transaction_type="expense",
                occurred_on=today,
                source="test",
            ),
            Transaction(
                amount=-800,
                category="cafe",
                description="Кофе",
                transaction_type="expense",
                occurred_on=today - timedelta(days=1),
                source="test",
            ),
            Transaction(
                amount=-25_000,
                category="investments",
                description="Акции",
                transaction_type="investment",
                occurred_on=today - timedelta(days=2),
                source="test",
            ),
            Transaction(
                amount=-10_000,
                category="savings",
                description="Вклад",
                transaction_type="savings",
                occurred_on=today - timedelta(days=3),
                source="test",
            ),
        ]
    )
    db.add(
        Subscription(
            name="Netflix",
            amount=999,
            last_used_date=today - timedelta(days=70),
            unused_days_threshold=60,
            next_billing_date=today + timedelta(days=3),
        )
    )
    await db.commit()
    return db


@pytest_asyncio.fixture
async def client(db_engine, seeded_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    Session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app(testing=True)

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
