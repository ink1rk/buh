from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import Base


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    apply_schema_extras(engine)


SCHEMA_HEAD = "0003_r7_integrity"
MIGRATION_LOCK = 8787002


def schema_revision(engine: Engine) -> str:
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
        if not exists:
            return ""
        row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return str(row or "")


def assert_schema_head(engine: Engine) -> str:
    revision = schema_revision(engine)
    if revision != SCHEMA_HEAD:
        raise RuntimeError(f"schema revision {revision or 'missing'} is not {SCHEMA_HEAD}")
    return revision


def _upgrade(engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import ROOT

    url = engine.url.render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def prepare_database(engine: Engine, mode: str = "create_all") -> None:
    """Tests may create tables directly. Only the migrate job runs Alembic, and it holds one lock."""
    if mode == "check":
        assert_schema_head(engine)
        return
    if mode == "migrate":
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK})
            conn.commit()
            try:
                if schema_revision(engine) != SCHEMA_HEAD:
                    _upgrade(engine)
                apply_schema_extras(engine)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK})
                conn.commit()
        return
    init_schema(engine)


def apply_schema_extras(engine: Engine) -> None:
    statements = [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_one_active
        ON publishing_outbox (post_id, channel_id)
        WHERE state IN ('scheduled', 'sending', 'retryable_failed', 'paused', 'needs_reconciliation')
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_classification_one_primary
        ON classifications (story_id)
        WHERE is_primary = true
        """,
        "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS draft_version INTEGER",
        "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
