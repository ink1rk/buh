"""Повторы задач и сохранённые представления

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-22 23:59:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_recurrence",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("cadence", sa.String(16), nullable=False),
        sa.Column("interval_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("weekday", sa.SmallInteger(), nullable=True),
        sa.Column("month_day", sa.SmallInteger(), nullable=True),
        sa.Column("priority", postgresql.ENUM("LOW", "MEDIUM", "HIGH", "CRITICAL", name="priority", create_type=False), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estimate_min", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_on", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("cadence IN ('daily', 'weekly', 'monthly')", name=op.f("ck_task_recurrence_cadence")),
        sa.CheckConstraint("interval_count >= 1", name=op.f("ck_task_recurrence_interval")),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], name=op.f("fk_task_recurrence_project_id_project"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["employee.id"], name=op.f("fk_task_recurrence_assignee_id_employee"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_recurrence")),
    )
    op.create_index("ix_task_recurrence_project_id", "task_recurrence", ["project_id"])
    op.add_column(
        "task",
        sa.Column("recurrence_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_task_recurrence_id_task_recurrence"),
        "task",
        "task_recurrence",
        ["recurrence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "saved_view",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("priority", sa.String(32), nullable=True),
        sa.Column("bucket", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"], name=op.f("fk_saved_view_user_id_user_account"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], name=op.f("fk_saved_view_project_id_project"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_view")),
    )
    op.create_index("ix_saved_view_user_id", "saved_view", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_view_user_id", table_name="saved_view")
    op.drop_table("saved_view")
    op.drop_constraint(op.f("fk_task_recurrence_id_task_recurrence"), "task", type_="foreignkey")
    op.drop_column("task", "recurrence_id")
    op.drop_index("ix_task_recurrence_project_id", table_name="task_recurrence")
    op.drop_table("task_recurrence")
