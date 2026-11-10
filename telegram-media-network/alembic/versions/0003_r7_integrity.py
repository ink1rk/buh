"""Bind cards to a post version and re-check stored license labels.

Revision ID: 0003_r7_integrity
Revises: 0002_endpoint_state
Create Date: 2026-11-10
"""

from alembic import op
from sqlalchemy.orm import Session

revision = "0003_r7_integrity"
down_revision = "0002_endpoint_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS draft_version INTEGER")
    op.execute("ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''")
    op.execute(
        """
        UPDATE media_assets AS asset
        SET draft_version = post.draft_version,
            content_hash = post.final_hash
        FROM posts AS post
        WHERE asset.post_id = post.id
          AND asset.kind = 'card'
          AND asset.status = 'ready'
          AND asset.file_path = 'post-' || post.id::text || '-v' || post.draft_version::text || '.jpg'
        """
    )
    op.execute(
        """
        UPDATE media_assets AS asset
        SET status = 'stale'
        FROM posts AS post
        WHERE asset.post_id = post.id
          AND asset.kind = 'card'
          AND asset.status = 'ready'
          AND (
            asset.draft_version IS NULL
            OR asset.draft_version <> post.draft_version
            OR asset.content_hash IS DISTINCT FROM post.final_hash
          )
        """
    )
    from app.services.licenses import reattest_licenses

    session = Session(bind=op.get_bind())
    reattest_licenses(session, commit=False)
    session.flush()


def downgrade() -> None:
    op.execute("ALTER TABLE media_assets DROP COLUMN IF EXISTS content_hash")
    op.execute("ALTER TABLE media_assets DROP COLUMN IF EXISTS draft_version")
