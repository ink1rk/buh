"""Уведомления пользователю

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22 23:55:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('assigned', 'status', 'comment', 'mention')",
            name=op.f("ck_notification_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user_account.id"],
            name=op.f("fk_notification_user_id_user_account"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_notification_project_id_project"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"],
            name=op.f("fk_notification_task_id_task"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
    )
    op.create_index("ix_notification_user_created", "notification", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_user_created", table_name="notification")
    op.drop_table("notification")
