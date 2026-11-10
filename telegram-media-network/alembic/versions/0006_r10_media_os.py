"""R10 media OS tables.

Revision ID: 0006_r10_media_os
Revises: 0005_r9_product_foundation
Create Date: 2026-11-10

Additive only. Downgrade drops the new tables and columns and is data-destructive.
Do not downgrade a database that already holds rows you need to keep.
0001–0005 are unchanged.
"""

from alembic import op

revision = "0006_r10_media_os"
down_revision = "0005_r9_product_foundation"
branch_labels = None
depends_on = None


_COLUMNS = (
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
)

_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS publisher_identities (
        id VARCHAR(80) PRIMARY KEY,
        title VARCHAR(160) DEFAULT '',
        kind VARCHAR(40) DEFAULT 'origin',
        trust INTEGER DEFAULT 8
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_snapshots (
        id SERIAL PRIMARY KEY,
        source_item_id INTEGER NOT NULL REFERENCES source_items(id),
        raw_hash VARCHAR(64) NOT NULL,
        body JSON DEFAULT '{}'::json,
        discovered_utc TIMESTAMPTZ,
        claimed_utc TIMESTAMPTZ,
        canonical_url TEXT DEFAULT '',
        origin_mode VARCHAR(40) DEFAULT 'demo'
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_source_snapshots_item ON source_snapshots (source_item_id, raw_hash)",
    """
    CREATE TABLE IF NOT EXISTS event_relations (
        id SERIAL PRIMARY KEY,
        left_cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
        right_cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
        relation VARCHAR(40) DEFAULT 'related',
        reason TEXT DEFAULT '',
        actor VARCHAR(80) DEFAULT '',
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS story_dossiers (
        id SERIAL PRIMARY KEY,
        cluster_id INTEGER NOT NULL UNIQUE REFERENCES story_clusters(id),
        summary TEXT DEFAULT '',
        timeline_json JSON DEFAULT '[]'::json,
        entities_json JSON DEFAULT '[]'::json,
        contradictions_json JSON DEFAULT '[]'::json,
        unknowns_json JSON DEFAULT '[]'::json,
        why_json JSON DEFAULT '{}'::json,
        valid_until TIMESTAMPTZ,
        license_note TEXT DEFAULT '',
        data_mode VARCHAR(20) DEFAULT 'demo',
        updated_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_mentions (
        id SERIAL PRIMARY KEY,
        cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
        kind VARCHAR(40) DEFAULT 'product',
        name VARCHAR(200) DEFAULT '',
        version VARCHAR(80) DEFAULT '',
        note TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claim_evidence (
        id SERIAL PRIMARY KEY,
        claim_row_id INTEGER NOT NULL REFERENCES editorial_claims(id),
        source_item_id INTEGER REFERENCES source_items(id),
        url TEXT DEFAULT '',
        excerpt VARCHAR(240) DEFAULT '',
        publisher_id VARCHAR(80) DEFAULT '',
        snapshot_utc TIMESTAMPTZ,
        method VARCHAR(80) DEFAULT '',
        actor VARCHAR(80) DEFAULT '',
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS editorial_briefs (
        id SERIAL PRIMARY KEY,
        cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
        channel_id VARCHAR(40) DEFAULT '',
        angle_id VARCHAR(40) DEFAULT 'news',
        format_id VARCHAR(40) DEFAULT 'breaking_news',
        prompt_version VARCHAR(40) DEFAULT 'editorial-v4',
        notes TEXT DEFAULT '',
        actor VARCHAR(80) DEFAULT '',
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS editorial_variants (
        id SERIAL PRIMARY KEY,
        brief_id INTEGER NOT NULL REFERENCES editorial_briefs(id),
        post_id INTEGER REFERENCES posts(id),
        angle_id VARCHAR(40) DEFAULT '',
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        text_hash VARCHAR(64) DEFAULT '',
        prompt_version VARCHAR(40) DEFAULT '',
        agent_role VARCHAR(40) DEFAULT 'editor',
        model_config_json JSON DEFAULT '{}'::json,
        claim_ids_json JSON DEFAULT '[]'::json,
        qa_json JSON DEFAULT '{}'::json,
        duration_ms INTEGER,
        cost INTEGER,
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS visual_presets (
        id VARCHAR(40) PRIMARY KEY,
        channel_id VARCHAR(40) DEFAULT '',
        purpose VARCHAR(40) DEFAULT 'news',
        ratio VARCHAR(16) DEFAULT '16:9',
        theme VARCHAR(16) DEFAULT 'dark',
        palette_json JSON DEFAULT '{}'::json
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_runs (
        id SERIAL PRIMARY KEY,
        story_id INTEGER,
        cluster_id INTEGER,
        channel_id VARCHAR(40) DEFAULT '',
        trace_id VARCHAR(64) DEFAULT '',
        idempotency_key VARCHAR(120) NOT NULL,
        stage VARCHAR(40) DEFAULT 'ingest',
        status VARCHAR(40) DEFAULT 'running',
        attempt INTEGER DEFAULT 1,
        last_error TEXT DEFAULT '',
        retry_after TIMESTAMPTZ,
        paused BOOLEAN NOT NULL DEFAULT false,
        editorial_ready BOOLEAN NOT NULL DEFAULT false,
        delivery_allowed BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ,
        lab_run_id INTEGER
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_idempotency ON workflow_runs (idempotency_key)",
    """
    CREATE TABLE IF NOT EXISTS workflow_steps (
        id SERIAL PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES workflow_runs(id),
        stage VARCHAR(40) NOT NULL,
        status VARCHAR(40) DEFAULT 'ok',
        attempt INTEGER DEFAULT 1,
        duration_ms INTEGER DEFAULT 0,
        last_error TEXT DEFAULT '',
        created_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS editorial_tasks (
        id SERIAL PRIMARY KEY,
        kind VARCHAR(40) DEFAULT 'research',
        cluster_id INTEGER,
        channel_id VARCHAR(40) DEFAULT '',
        title TEXT DEFAULT '',
        status VARCHAR(40) DEFAULT 'open',
        assignee VARCHAR(80) DEFAULT '',
        reason TEXT DEFAULT '',
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metric_provenance (
        id SERIAL PRIMARY KEY,
        observation_id INTEGER NOT NULL REFERENCES metric_observations(id),
        source_type VARCHAR(40) DEFAULT 'unknown',
        evidence TEXT DEFAULT '',
        actor VARCHAR(80) DEFAULT '',
        collected_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commercial_offers (
        id SERIAL PRIMARY KEY,
        lead_id INTEGER REFERENCES sales_leads(id),
        title VARCHAR(200) DEFAULT '',
        status VARCHAR(40) DEFAULT 'draft',
        currency VARCHAR(8) DEFAULT 'RUB',
        price INTEGER,
        price_kind VARCHAR(40) DEFAULT 'proposal',
        notes TEXT DEFAULT '',
        demo BOOLEAN NOT NULL DEFAULT true,
        history_json JSON DEFAULT '[]'::json,
        created_at TIMESTAMPTZ,
        lab_run_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commercial_line_items (
        id SERIAL PRIMARY KEY,
        offer_id INTEGER NOT NULL REFERENCES commercial_offers(id),
        package VARCHAR(40) DEFAULT 'single',
        channel_id VARCHAR(40) DEFAULT '',
        materials_count INTEGER DEFAULT 1,
        slot_utc TIMESTAMPTZ,
        price INTEGER,
        status VARCHAR(40) DEFAULT 'proposed'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lab_runs (
        id SERIAL PRIMARY KEY,
        title VARCHAR(160) DEFAULT 'offline-30d',
        started_at TIMESTAMPTZ,
        through_day INTEGER DEFAULT 30,
        status VARCHAR(40) DEFAULT 'ready',
        report_json JSON DEFAULT '{}'::json,
        data_mode VARCHAR(20) DEFAULT 'demo'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_plan_settings (
        channel_id VARCHAR(40) PRIMARY KEY,
        daily_cap INTEGER DEFAULT 2,
        quiet_start VARCHAR(5) DEFAULT '22:00',
        quiet_end VARCHAR(5) DEFAULT '08:00',
        mix_fresh_pct INTEGER DEFAULT 70,
        min_gap_minutes INTEGER DEFAULT 240,
        blackout_dates_json JSON DEFAULT '[]'::json,
        theme_days_json JSON DEFAULT '[]'::json,
        reserve_slots INTEGER DEFAULT 1,
        updated_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS score_revisions (
        id SERIAL PRIMARY KEY,
        cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
        channel_id VARCHAR(40) DEFAULT '',
        formula_version VARCHAR(40) DEFAULT 'rank-v4',
        weights_json JSON DEFAULT '{}'::json,
        dimensions_json JSON DEFAULT '{}'::json,
        total INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ
    )
    """,
)


def upgrade() -> None:
    for statement in _COLUMNS:
        op.execute(statement)
    for statement in _TABLES:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("0006 cannot be downgraded without dropping editorial history; use a forward fix")
