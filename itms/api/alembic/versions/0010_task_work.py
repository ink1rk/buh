"""Комментарии и чеклист задачи

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22 23:50:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_comment",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"],
            name=op.f("fk_task_comment_task_id_task"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_comment")),
    )
    op.create_index("ix_task_comment_task_id", "task_comment", ["task_id"])
    op.create_table(
        "task_check",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"],
            name=op.f("fk_task_check_task_id_task"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_check")),
    )
    op.create_index("ix_task_check_task_id", "task_check", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_check_task_id", table_name="task_check")
    op.drop_table("task_check")
    op.drop_index("ix_task_comment_task_id", table_name="task_comment")
    op.drop_table("task_comment")
