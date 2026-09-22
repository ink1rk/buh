"""План помещения: стойки и щиты в миллиметрах

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-22 22:40:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "floorplan",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("width_mm", sa.Integer(), nullable=False),
        sa.Column("height_mm", sa.Integer(), nullable=False),
        sa.Column("background_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scale_px_per_m", sa.Numeric(8, 3), nullable=True),
        sa.ForeignKeyConstraint(
            ["location_id"], ["location.id"],
            name=op.f("fk_floorplan_location_id_location"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["background_file_id"], ["file_object.id"],
            name=op.f("fk_floorplan_background_file_id_file_object"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_floorplan")),
    )
    op.create_index("ix_floorplan_location_id", "floorplan", ["location_id"])
    op.create_table(
        "floorplan_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("floorplan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ci_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("item_kind", sa.String(16), nullable=False),
        sa.Column("x", sa.Numeric(9, 2), nullable=False),
        sa.Column("y", sa.Numeric(9, 2), nullable=False),
        sa.Column("width", sa.Numeric(9, 2), nullable=False),
        sa.Column("height", sa.Numeric(9, 2), nullable=False),
        sa.Column("rotation", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("style", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint(
            "item_kind IN ('RACK', 'DEVICE', 'POWER', 'ANNOTATION', 'ROUTE')",
            name="ck_floorplan_item_kind",
        ),
        sa.CheckConstraint("rotation IN (0, 90, 180, 270)", name="ck_floorplan_item_rotation"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_floorplan_item_size"),
        sa.ForeignKeyConstraint(
            ["floorplan_id"], ["floorplan.id"],
            name=op.f("fk_floorplan_item_floorplan_id_floorplan"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ci_id"], ["ci.id"],
            name=op.f("fk_floorplan_item_ci_id_ci"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_floorplan_item")),
    )
    op.create_index("ix_floorplan_item_floorplan_id", "floorplan_item", ["floorplan_id"])
    op.create_index(
        "uq_floorplan_item_ci",
        "floorplan_item",
        ["floorplan_id", "ci_id"],
        unique=True,
        postgresql_where=sa.text("ci_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_floorplan_item_ci", table_name="floorplan_item")
    op.drop_index("ix_floorplan_item_floorplan_id", table_name="floorplan_item")
    op.drop_table("floorplan_item")
    op.drop_index("ix_floorplan_location_id", table_name="floorplan")
    op.drop_table("floorplan")
