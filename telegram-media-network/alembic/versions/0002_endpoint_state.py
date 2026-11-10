"""Per-URL conditional cache and component heartbeats.

Revision ID: 0002_endpoint_state
Revises: 0001_initial
Create Date: 2026-11-10
"""

from alembic import op

revision = "0002_endpoint_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_endpoint_states (
            id SERIAL PRIMARY KEY,
            source_id VARCHAR(80) NOT NULL REFERENCES sources(id),
            request_url TEXT NOT NULL,
            etag TEXT DEFAULT '',
            last_modified TEXT DEFAULT '',
            last_status INTEGER DEFAULT 0,
            last_checked_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_source_endpoint
        ON source_endpoint_states (source_id, request_url)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS component_heartbeats (
            name VARCHAR(40) PRIMARY KEY,
            status VARCHAR(40) DEFAULT 'unknown',
            detail TEXT DEFAULT '',
            beat_at TIMESTAMPTZ NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS component_heartbeats")
    op.execute("DROP TABLE IF EXISTS source_endpoint_states")
