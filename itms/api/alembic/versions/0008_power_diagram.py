"""Однолинейная схема: тип POWER и ребро на power_link

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-22 22:10:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE diagram_type ADD VALUE IF NOT EXISTS 'POWER'")
    op.add_column(
        "diagram_edge",
        sa.Column("power_link_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_diagram_edge_power_link_id_power_link"),
        "diagram_edge",
        "power_link",
        ["power_link_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("ALTER TABLE diagram_edge DROP CONSTRAINT ck_diagram_edge_one_backing")
    op.execute(
        "ALTER TABLE diagram_edge ADD CONSTRAINT ck_diagram_edge_one_backing "
        "CHECK (num_nonnulls(connection_id, relation_id, power_link_id) <= 1)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE diagram_edge DROP CONSTRAINT ck_diagram_edge_one_backing")
    op.execute(
        "ALTER TABLE diagram_edge ADD CONSTRAINT ck_diagram_edge_one_backing "
        "CHECK (num_nonnulls(connection_id, relation_id) <= 1)"
    )
    op.drop_constraint(
        op.f("fk_diagram_edge_power_link_id_power_link"),
        "diagram_edge",
        type_="foreignkey",
    )
    op.drop_column("diagram_edge", "power_link_id")
