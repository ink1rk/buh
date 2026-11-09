from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.db import init_schema, make_engine, make_session_factory
from app.core.models import Base
from app.main import create_app
from app.services.bootstrap import bootstrap
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

URL = "postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_test"


def make_settings() -> Settings:
    return Settings(
        environment="test",
        dry_run=True,
        publish_enabled=False,
        global_kill_switch=True,
        sponsored_enabled=False,
        database_url=URL,
        session_secret="test-session-secret-value-32",
        llm_mode="mock",
        source_mode="offline",
        telegram_bot_token="",
        github_read_token="",
        hf_read_token="",
    )


@pytest.fixture(scope="session")
def engine():
    db_engine = make_engine(URL)
    init_schema(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture(autouse=True)
def clean(engine):
    _truncate(engine)
    yield
    _truncate(engine)


@pytest.fixture
def db(engine) -> Session:
    factory = make_session_factory(engine)
    session = factory()
    bootstrap(session, make_settings())
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(engine):
    del engine
    application = create_app(make_settings(), init_db=True)
    with TestClient(application) as test_client:
        yield test_client


def _truncate(db_engine) -> None:
    names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
