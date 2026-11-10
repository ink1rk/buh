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


SCHEMA_HEAD = "0006_r10_media_os"
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
        "ALTER TABLE publishing_outbox ADD COLUMN IF NOT EXISTS claimed_draft_version INTEGER",
        "ALTER TABLE publishing_outbox ADD COLUMN IF NOT EXISTS claimed_caption TEXT DEFAULT ''",
        "ALTER TABLE ad_campaigns ADD COLUMN IF NOT EXISTS demo BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS event_type VARCHAR(40) DEFAULT 'event'",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS last_change_at TIMESTAMPTZ",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS dossier_json JSON DEFAULT '{}'::json",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS score_version VARCHAR(40) DEFAULT 'radar-v3'",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS origin VARCHAR(40) DEFAULT 'propose'",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS format_id VARCHAR(40) DEFAULT ''",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS format_id VARCHAR(40) DEFAULT 'breaking_news'",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS quality_json JSON DEFAULT '{}'::json",
        "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS publisher_id VARCHAR(80) DEFAULT ''",
        "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS content_kind VARCHAR(40) DEFAULT 'news'",
        "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS origin_mode VARCHAR(40) DEFAULT 'demo'",
        "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS angle_id VARCHAR(40) DEFAULT ''",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS brief_id INTEGER",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS text_hash VARCHAR(64) DEFAULT ''",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS data_mode VARCHAR(20) DEFAULT 'demo'",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS trend_state VARCHAR(40) DEFAULT 'unknown'",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS trend_delta INTEGER",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS data_mode VARCHAR(20) DEFAULT 'demo'",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS program_kind VARCHAR(40) DEFAULT 'breaking'",
        "ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
        "ALTER TABLE ranked_candidates ADD COLUMN IF NOT EXISTS trend_state VARCHAR(40) DEFAULT 'unknown'",
        "ALTER TABLE ranked_candidates ADD COLUMN IF NOT EXISTS reasons_json JSON DEFAULT '[]'::json",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS program_kind VARCHAR(40) DEFAULT 'breaking'",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS vacancy_reason TEXT DEFAULT ''",
        "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS tone TEXT DEFAULT ''",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS length_chars INTEGER DEFAULT 900",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS frequency TEXT DEFAULT ''",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS stopwords_json JSON DEFAULT '[]'::json",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS link_format TEXT DEFAULT ''",
        "ALTER TABLE channel_editorial_profiles ADD COLUMN IF NOT EXISTS risks_json JSON DEFAULT '[]'::json",
        "ALTER TABLE editorial_claims ADD COLUMN IF NOT EXISTS method VARCHAR(80) DEFAULT ''",
        "ALTER TABLE editorial_claims ADD COLUMN IF NOT EXISTS actor VARCHAR(80) DEFAULT ''",
        "ALTER TABLE editorial_claims ADD COLUMN IF NOT EXISTS cluster_id INTEGER",
        "ALTER TABLE editorial_claims ADD COLUMN IF NOT EXISTS excerpt VARCHAR(240) DEFAULT ''",
        "ALTER TABLE editorial_claims ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ",
        "ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS unit VARCHAR(40) DEFAULT 'count'",
        "ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS interval VARCHAR(40) DEFAULT 'snapshot'",
        "ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS actor VARCHAR(80) DEFAULT ''",
        "ALTER TABLE experiment_plans ADD COLUMN IF NOT EXISTS segment VARCHAR(80) DEFAULT ''",
        "ALTER TABLE experiment_plans ADD COLUMN IF NOT EXISTS format_id VARCHAR(40) DEFAULT ''",
        "ALTER TABLE experiment_plans ADD COLUMN IF NOT EXISTS period VARCHAR(80) DEFAULT ''",
        "ALTER TABLE experiment_plans ADD COLUMN IF NOT EXISTS control TEXT DEFAULT ''",
        "ALTER TABLE experiment_plans ADD COLUMN IF NOT EXISTS confidence_note TEXT DEFAULT ''",
        "ALTER TABLE sales_leads ADD COLUMN IF NOT EXISTS owner VARCHAR(80) DEFAULT ''",
        "ALTER TABLE sales_leads ADD COLUMN IF NOT EXISTS next_action_at TIMESTAMPTZ",
        "ALTER TABLE sales_leads ADD COLUMN IF NOT EXISTS offer_version INTEGER DEFAULT 1",
        "ALTER TABLE sales_leads ADD COLUMN IF NOT EXISTS history_json JSON DEFAULT '[]'::json",
        "ALTER TABLE sales_leads ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
        "ALTER TABLE rate_cards ADD COLUMN IF NOT EXISTS channels_json JSON DEFAULT '[]'::json",
        "ALTER TABLE rate_cards ADD COLUMN IF NOT EXISTS materials_count INTEGER DEFAULT 1",
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
