"""Editorial radar, programs, and measured analytics.

Revision ID: 0004_global_product
Revises: 0003_r7_integrity
Create Date: 2026-11-10

Additive only. Downgrade drops the new tables and the two outbox columns.
Do not downgrade a database that already holds rows you need to keep.
"""

from alembic import op

revision = "0004_global_product"
down_revision = "0003_r7_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE publishing_outbox ADD COLUMN IF NOT EXISTS claimed_draft_version INTEGER")
    op.execute("ALTER TABLE publishing_outbox ADD COLUMN IF NOT EXISTS claimed_caption TEXT DEFAULT ''")
    op.execute("ALTER TABLE ad_campaigns ADD COLUMN IF NOT EXISTS demo BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS story_clusters (
            id SERIAL PRIMARY KEY,
            cluster_key VARCHAR(300) NOT NULL,
            title TEXT DEFAULT '',
            kind VARCHAR(40) DEFAULT 'event',
            status VARCHAR(40) DEFAULT 'open',
            list_name VARCHAR(40) DEFAULT 'review',
            primary_channel_id VARCHAR(40) DEFAULT '',
            first_seen TIMESTAMPTZ,
            last_seen TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            merge_reason TEXT DEFAULT '',
            manual_override BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT uq_cluster_key UNIQUE (cluster_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_story_clusters_status ON story_clusters (status)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_members (
            id SERIAL PRIMARY KEY,
            cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
            story_id INTEGER REFERENCES stories(id),
            source_item_id INTEGER REFERENCES source_items(id),
            relation VARCHAR(40) DEFAULT 'member',
            reason TEXT DEFAULT ''
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cluster_members_cluster ON cluster_members (cluster_id, relation)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ranked_candidates (
            id SERIAL PRIMARY KEY,
            cluster_id INTEGER NOT NULL REFERENCES story_clusters(id),
            channel_id VARCHAR(40) NOT NULL,
            model_version VARCHAR(40) DEFAULT 'radar-v2',
            computed_at TIMESTAMPTZ,
            dimensions_json JSON,
            penalties_json JSON,
            rank_score INTEGER DEFAULT 0,
            confidence INTEGER DEFAULT 0,
            explanation TEXT DEFAULT '',
            status VARCHAR(40) DEFAULT 'ranked',
            CONSTRAINT uq_rank_latest UNIQUE (cluster_id, channel_id, model_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trend_samples (
            id SERIAL PRIMARY KEY,
            source_item_id INTEGER NOT NULL REFERENCES source_items(id),
            snapshot_utc TIMESTAMPTZ NOT NULL,
            metric_name VARCHAR(80) NOT NULL,
            value INTEGER,
            provider VARCHAR(80) DEFAULT '',
            completeness VARCHAR(40) DEFAULT 'single'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_trend_samples_item ON trend_samples (source_item_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_snapshots (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id),
            draft_version INTEGER NOT NULL,
            claim_id VARCHAR(80) DEFAULT '',
            claim_text TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            source_item_id INTEGER REFERENCES source_items(id),
            published_at TIMESTAMPTZ,
            observed_at TIMESTAMPTZ,
            verified_at TIMESTAMPTZ,
            verification_method VARCHAR(40) DEFAULT '',
            support_level VARCHAR(40) DEFAULT 'source_claim',
            excerpt VARCHAR(200) DEFAULT '',
            origin_kind VARCHAR(40) DEFAULT 'source_claim'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_evidence_post_version ON evidence_snapshots (post_id, draft_version)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS series (
            id VARCHAR(40) PRIMARY KEY,
            title VARCHAR(160) NOT NULL,
            allowed_channels JSON,
            period VARCHAR(20) DEFAULT 'daily',
            timezone VARCHAR(64) DEFAULT 'Europe/Moscow',
            min_items INTEGER DEFAULT 1,
            max_items INTEGER DEFAULT 5,
            style VARCHAR(40) DEFAULT 'digest',
            rules_json JSON,
            enabled BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            series_id VARCHAR(40) NOT NULL REFERENCES series(id),
            channel_id VARCHAR(40) NOT NULL,
            slot_utc TIMESTAMPTZ NOT NULL,
            status VARCHAR(40) DEFAULT 'proposed',
            item_refs JSON,
            draft_post_id INTEGER REFERENCES posts(id),
            reason TEXT DEFAULT '',
            version INTEGER DEFAULT 1
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_episodes_slot ON episodes (channel_id, slot_utc)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS editorial_feedback (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id),
            reviewer_id INTEGER REFERENCES users(id),
            rating VARCHAR(40) DEFAULT '',
            labels_json JSON,
            comment TEXT DEFAULT '',
            created_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_editorial_feedback_post ON editorial_feedback (post_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audience_metrics (
            id SERIAL PRIMARY KEY,
            channel_id VARCHAR(40) NOT NULL,
            message_id VARCHAR(40) DEFAULT '',
            period_at TIMESTAMPTZ NOT NULL,
            kind VARCHAR(40) NOT NULL,
            value INTEGER,
            measurement_source VARCHAR(40) DEFAULT 'manual',
            verified_by VARCHAR(80) DEFAULT '',
            created_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            campaign_id INTEGER NOT NULL REFERENCES ad_campaigns(id),
            channel_id VARCHAR(40) DEFAULT '',
            slot_utc TIMESTAMPTZ,
            status VARCHAR(40) DEFAULT 'planned',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_campaign ON bookings (campaign_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creatives (
            id SERIAL PRIMARY KEY,
            campaign_id INTEGER NOT NULL REFERENCES ad_campaigns(id),
            body TEXT DEFAULT '',
            disclosure_status VARCHAR(40) DEFAULT 'pending',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS placements (
            id SERIAL PRIMARY KEY,
            booking_id INTEGER NOT NULL REFERENCES bookings(id),
            creative_id INTEGER NOT NULL REFERENCES creatives(id),
            status VARCHAR(40) DEFAULT 'planned',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_events (
            id SERIAL PRIMARY KEY,
            campaign_id INTEGER NOT NULL REFERENCES ad_campaigns(id),
            kind VARCHAR(20) DEFAULT 'planned',
            amount INTEGER,
            currency VARCHAR(8) DEFAULT 'RUB',
            note TEXT DEFAULT '',
            demo BOOLEAN NOT NULL DEFAULT true
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS finance_events")
    op.execute("DROP TABLE IF EXISTS placements")
    op.execute("DROP TABLE IF EXISTS creatives")
    op.execute("DROP TABLE IF EXISTS bookings")
    op.execute("DROP TABLE IF EXISTS audience_metrics")
    op.execute("DROP TABLE IF EXISTS editorial_feedback")
    op.execute("DROP TABLE IF EXISTS episodes")
    op.execute("DROP TABLE IF EXISTS series")
    op.execute("DROP TABLE IF EXISTS evidence_snapshots")
    op.execute("DROP TABLE IF EXISTS trend_samples")
    op.execute("DROP TABLE IF EXISTS ranked_candidates")
    op.execute("DROP TABLE IF EXISTS cluster_members")
    op.execute("DROP TABLE IF EXISTS story_clusters")
    op.execute("ALTER TABLE publishing_outbox DROP COLUMN IF EXISTS claimed_caption")
    op.execute("ALTER TABLE publishing_outbox DROP COLUMN IF EXISTS claimed_draft_version")
    op.execute("ALTER TABLE ad_campaigns DROP COLUMN IF EXISTS demo")
