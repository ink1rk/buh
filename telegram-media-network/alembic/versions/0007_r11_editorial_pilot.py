"""R11 editorial factory and chronological lab.

Revision ID: 0007_r11_editorial_pilot
Revises: 0006_r10_media_os
Create Date: 2026-11-10

Additive only. Downgrade would drop editorial lineage, daily lab snapshots and
LLM call logs. Do not downgrade a database that already holds rows you need.
0001–0006 are unchanged.
"""

from alembic import op

revision = "0007_r11_editorial_pilot"
down_revision = "0006_r10_media_os"
branch_labels = None
depends_on = None


_COLUMNS = (
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS template_version VARCHAR(40) DEFAULT 'studio-v3'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS ratio VARCHAR(16) DEFAULT '16:9'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS qa_status VARCHAR(40) DEFAULT 'pending'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS source_license VARCHAR(80) DEFAULT 'own_typographic_template'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS generator_mode VARCHAR(40) DEFAULT 'local_template'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS alt_text TEXT DEFAULT ''",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS purpose VARCHAR(40) DEFAULT 'news'",
    "ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
    "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS calendar_status VARCHAR(40) DEFAULT 'proposed'",
    "ALTER TABLE editorial_briefs ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
    "ALTER TABLE editorial_variants ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS post_id INTEGER",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS brief_id INTEGER",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS asset_id INTEGER",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS episode_id INTEGER",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS ready_for_human BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS ready_for_delivery BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS lineage_json JSON DEFAULT '{}'::json",
    "ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS input_hash VARCHAR(64) DEFAULT ''",
    "ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS output_ref VARCHAR(160) DEFAULT ''",
    "ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS error_class VARCHAR(40) DEFAULT ''",
    "ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS skipped_reason TEXT DEFAULT ''",
    "ALTER TABLE editorial_tasks ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ",
    "ALTER TABLE editorial_tasks ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'normal'",
    "ALTER TABLE editorial_tasks ADD COLUMN IF NOT EXISTS lab_run_id INTEGER",
    "ALTER TABLE editorial_tasks ADD COLUMN IF NOT EXISTS post_id INTEGER",
    "ALTER TABLE lab_runs ADD COLUMN IF NOT EXISTS mode VARCHAR(40) DEFAULT 'historical-small'",
    "ALTER TABLE lab_runs ADD COLUMN IF NOT EXISTS current_day INTEGER DEFAULT 0",
    "ALTER TABLE lab_runs ADD COLUMN IF NOT EXISTS clock_json JSON DEFAULT '{}'::json",
    "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ",
    "ALTER TABLE source_items ADD COLUMN IF NOT EXISTS cassette_id VARCHAR(80) DEFAULT ''",
)

_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS lab_daily_snapshots (
        id SERIAL PRIMARY KEY,
        lab_run_id INTEGER NOT NULL REFERENCES lab_runs(id),
        day INTEGER NOT NULL,
        as_of TIMESTAMPTZ,
        stats_json JSON DEFAULT '{}'::json,
        data_mode VARCHAR(20) DEFAULT 'demo',
        CONSTRAINT uq_lab_daily_run_day UNIQUE (lab_run_id, day)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_call_logs (
        id SERIAL PRIMARY KEY,
        role VARCHAR(40) DEFAULT '',
        mode VARCHAR(20) DEFAULT 'mock',
        model_id VARCHAR(80) DEFAULT '',
        prompt_version VARCHAR(40) DEFAULT '',
        status VARCHAR(40) DEFAULT 'ok',
        error TEXT DEFAULT '',
        duration_ms INTEGER DEFAULT 0,
        fallback_mode VARCHAR(40) DEFAULT '',
        local_attempted BOOLEAN NOT NULL DEFAULT false,
        payload_json JSON DEFAULT '{}'::json,
        created_at TIMESTAMPTZ,
        lab_run_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_catalog (
        id VARCHAR(80) PRIMARY KEY,
        title VARCHAR(200) DEFAULT '',
        kind VARCHAR(40) DEFAULT 'rss',
        homepage TEXT DEFAULT '',
        collector VARCHAR(80) DEFAULT '',
        enabled BOOLEAN NOT NULL DEFAULT true,
        live_allowed BOOLEAN NOT NULL DEFAULT false,
        last_status VARCHAR(40) DEFAULT 'cassette',
        cassette_path TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    )
    """,
)


def upgrade() -> None:
    for statement in _COLUMNS:
        op.execute(statement)
    for statement in _TABLES:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("0007 cannot be downgraded without dropping editorial lineage; use a forward fix")
