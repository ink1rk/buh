"""Места комплектующих и строки бюджета

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-28 18:20:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _actor_keys(table: str, *, create: bool) -> None:
    for column in ("created_by", "updated_by"):
        name = f"fk_{table}_{column}_user_account"
        if create:
            op.create_foreign_key(
                name, table, "user_account", [column], ["id"], ondelete="SET NULL"
            )
        else:
            op.drop_constraint(name, table, type_="foreignkey")


def upgrade() -> None:
    op.add_column("device_part", sa.Column("slots", postgresql.JSONB(), nullable=True))
    op.create_table(
        "finance_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("article", sa.String(255), nullable=False),
        sa.Column("planned", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("actual", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('BUDGET', 'CASHFLOW')",
            name=op.f("ck_finance_entry_kind"),
        ),
        sa.CheckConstraint(
            "direction IN ('IN', 'OUT')",
            name=op.f("ck_finance_entry_direction"),
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name=op.f("fk_finance_entry_department_id_department"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_entry")),
    )
    op.create_index("ix_finance_entry_period", "finance_entry", ["kind", "period"])
    _actor_keys("finance_entry", create=True)


def downgrade() -> None:
    _actor_keys("finance_entry", create=False)
    op.drop_index("ix_finance_entry_period", table_name="finance_entry")
    op.drop_table("finance_entry")
    op.drop_column("device_part", "slots")
