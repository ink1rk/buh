"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-10
"""

from alembic import op

from app.core.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_one_active
        ON publishing_outbox (post_id, channel_id)
        WHERE state IN ('scheduled', 'sending', 'retryable_failed', 'paused', 'needs_reconciliation')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_classification_one_primary
        ON classifications (story_id)
        WHERE is_primary = true
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
