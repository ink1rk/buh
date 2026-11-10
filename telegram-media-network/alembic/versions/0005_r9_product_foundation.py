"""R9 editorial platform tables.

Revision ID: 0005_r9_product_foundation
Revises: 0004_global_product
Create Date: 2026-11-10

Additive only. Downgrade drops the new tables and columns.
Do not downgrade a database that already holds rows you need to keep.
0001–0004 are unchanged.
"""

from alembic import op

revision = "0005_r9_product_foundation"
down_revision = "0004_global_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS event_type VARCHAR(40) DEFAULT 'event'")
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ")
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS last_change_at TIMESTAMPTZ")
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS dossier_json JSON DEFAULT '{}'::json")
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS score_version VARCHAR(40) DEFAULT 'radar-v3'")
    op.execute("ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS locked BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS origin VARCHAR(40) DEFAULT 'propose'")
    op.execute("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS format_id VARCHAR(40) DEFAULT ''")
    op.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS format_id VARCHAR(40) DEFAULT 'breaking_news'")
    op.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS quality_json JSON DEFAULT '{}'::json")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_editorial_profiles (
            channel_id VARCHAR(40) PRIMARY KEY,
            version INTEGER DEFAULT 1,
            audience TEXT DEFAULT '',
            promise TEXT DEFAULT '',
            rubrics_json JSON DEFAULT '[]'::json,
            avoid_json JSON DEFAULT '[]'::json,
            voice TEXT DEFAULT '',
            formats_json JSON DEFAULT '[]'::json,
            evidence_rules_json JSON DEFAULT '{}'::json,
            palette_json JSON DEFAULT '{}'::json,
            updated_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS editorial_claims (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id),
            draft_version INTEGER NOT NULL,
            claim_id VARCHAR(80) NOT NULL,
            text TEXT DEFAULT '',
            status VARCHAR(40) DEFAULT 'not_checked',
            evidence_url TEXT DEFAULT '',
            reviewer VARCHAR(80) DEFAULT '',
            checked_at TIMESTAMPTZ,
            origin_kind VARCHAR(40) DEFAULT 'source_claim'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_claims_post_version ON editorial_claims (post_id, draft_version)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS story_relations (
            id SERIAL PRIMARY KEY,
            left_cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
            right_cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
            relation VARCHAR(40) DEFAULT 'merge_candidate',
            reason TEXT DEFAULT '',
            actor VARCHAR(80) DEFAULT '',
            created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS metric_definitions (
            id VARCHAR(80) PRIMARY KEY,
            title VARCHAR(160) DEFAULT '',
            unit VARCHAR(40) DEFAULT 'count',
            formula TEXT DEFAULT '',
            source_type VARCHAR(40) DEFAULT 'derived'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS metric_observations (
            id SERIAL PRIMARY KEY,
            metric_id VARCHAR(80) NOT NULL REFERENCES metric_definitions(id),
            channel_id VARCHAR(40) DEFAULT '',
            period_at TIMESTAMPTZ NOT NULL,
            value INTEGER,
            source_type VARCHAR(40) DEFAULT 'unknown',
            collected_at TIMESTAMPTZ,
            evidence_ref TEXT DEFAULT '',
            demo BOOLEAN NOT NULL DEFAULT false
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_plans (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) DEFAULT '',
            hypothesis TEXT DEFAULT '',
            expected_metric VARCHAR(80) DEFAULT '',
            status VARCHAR(40) DEFAULT 'NOT_STARTED',
            actual TEXT DEFAULT 'н/д',
            decision TEXT DEFAULT '',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sales_leads (
            id SERIAL PRIMARY KEY,
            advertiser VARCHAR(200) DEFAULT '',
            segment VARCHAR(80) DEFAULT '',
            stage VARCHAR(40) DEFAULT 'lead',
            channel_id VARCHAR(40) DEFAULT '',
            notes TEXT DEFAULT '',
            demo BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_cards (
            id SERIAL PRIMARY KEY,
            title VARCHAR(160) DEFAULT '',
            package VARCHAR(40) DEFAULT 'single',
            price INTEGER,
            currency VARCHAR(8) DEFAULT 'RUB',
            status VARCHAR(40) DEFAULT 'draft',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_records (
            id SERIAL PRIMARY KEY,
            kind VARCHAR(40) DEFAULT 'infra',
            amount INTEGER,
            currency VARCHAR(8) DEFAULT 'RUB',
            note TEXT DEFAULT '',
            demo BOOLEAN NOT NULL DEFAULT true,
            period_at TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_records")
    op.execute("DROP TABLE IF EXISTS rate_cards")
    op.execute("DROP TABLE IF EXISTS sales_leads")
    op.execute("DROP TABLE IF EXISTS experiment_plans")
    op.execute("DROP TABLE IF EXISTS metric_observations")
    op.execute("DROP TABLE IF EXISTS metric_definitions")
    op.execute("DROP TABLE IF EXISTS story_relations")
    op.execute("DROP TABLE IF EXISTS editorial_claims")
    op.execute("DROP TABLE IF EXISTS channel_editorial_profiles")
    op.execute("ALTER TABLE posts DROP COLUMN IF EXISTS quality_json")
    op.execute("ALTER TABLE posts DROP COLUMN IF EXISTS format_id")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS format_id")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS origin")
    op.execute("ALTER TABLE episodes DROP COLUMN IF EXISTS locked")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS locked")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS score_version")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS dossier_json")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS last_change_at")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS event_at")
    op.execute("ALTER TABLE story_clusters DROP COLUMN IF EXISTS event_type")
