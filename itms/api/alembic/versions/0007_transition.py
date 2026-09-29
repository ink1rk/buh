"""Снимок состояния и план изменения модели

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-22 21:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "state_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("taken_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_state_snapshot_project_id_project"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["taken_by"], ["user_account.id"],
            name=op.f("fk_state_snapshot_taken_by_user_account"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_state_snapshot")),
    )
    op.create_index("ix_state_snapshot_project_id", "state_snapshot", ["project_id"])

    op.create_table(
        "planned_change",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'REVIEW', 'APPROVED', 'APPLYING', 'APPLIED', 'CANCELLED')",
            name="ck_planned_change_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_planned_change_project_id_project"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["base_snapshot_id"], ["state_snapshot.id"],
            name=op.f("fk_planned_change_base_snapshot_id_state_snapshot"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["result_snapshot_id"], ["state_snapshot.id"],
            name=op.f("fk_planned_change_result_snapshot_id_state_snapshot"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_change")),
    )
    op.create_index("ix_planned_change_project_id", "planned_change", ["project_id"])

    op.create_table(
        "change_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("planned_change_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("apply_status", sa.String(16), nullable=False),
        sa.Column("applied_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "operation IN ('CREATE', 'UPDATE', 'DELETE', 'MOVE', 'CONNECT', 'DISCONNECT')",
            name="ck_change_item_operation",
        ),
        sa.CheckConstraint(
            "apply_status IN ('PENDING', 'APPLIED', 'SKIPPED', 'FAILED')",
            name="ck_change_item_apply_status",
        ),
        sa.ForeignKeyConstraint(
            ["planned_change_id"], ["planned_change.id"],
            name=op.f("fk_change_item_planned_change_id_planned_change"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_item")),
    )
    op.create_index("ix_change_item_planned_change_id", "change_item", ["planned_change_id"])


def downgrade() -> None:
    op.drop_table("change_item")
    op.drop_table("planned_change")
    op.drop_index("ix_state_snapshot_project_id", table_name="state_snapshot")
    op.drop_table("state_snapshot")
