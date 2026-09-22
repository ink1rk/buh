"""Стойки и размещение по юнитам

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22 16:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FORM_FACTOR = postgresql.ENUM(
    "CABINET", "OPEN_FRAME", "WALL", name="rack_form_factor", create_type=False
)
RACK_FACE = postgresql.ENUM("FRONT", "REAR", "FULL", name="rack_face", create_type=False)
ZERO_U = postgresql.ENUM("LEFT", "RIGHT", name="zero_u_side", create_type=False)


def upgrade() -> None:
    op.execute("CREATE TYPE rack_form_factor AS ENUM ('CABINET', 'OPEN_FRAME', 'WALL')")
    op.execute("CREATE TYPE rack_face AS ENUM ('FRONT', 'REAR', 'FULL')")
    op.execute("CREATE TYPE zero_u_side AS ENUM ('LEFT', 'RIGHT')")

    op.create_table(
        "rack",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("u_height", sa.SmallInteger(), server_default=sa.text("42"), nullable=False),
        sa.Column("width_in", sa.SmallInteger(), server_default=sa.text("19"), nullable=False),
        sa.Column("depth_mm", sa.Integer(), server_default=sa.text("1000"), nullable=False),
        sa.Column("max_weight_kg", sa.Numeric(7, 2), nullable=True),
        sa.Column("max_power_w", sa.Integer(), nullable=True),
        sa.Column("form_factor", FORM_FACTOR, server_default="CABINET", nullable=False),
        sa.Column("descending_units", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("plan_x", sa.Numeric(8, 2), nullable=True),
        sa.Column("plan_y", sa.Numeric(8, 2), nullable=True),
        sa.Column("plan_rotation", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("u_height BETWEEN 1 AND 60", name=op.f("ck_rack_u_height")),
        sa.ForeignKeyConstraint(["id"], ["ci.id"], name=op.f("fk_rack_id_ci"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rack")),
    )
    op.create_table(
        "rack_mount",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("rack_id", sa.UUID(), nullable=False),
        sa.Column("ci_id", sa.UUID(), nullable=False),
        sa.Column("position_u", sa.SmallInteger(), nullable=False),
        sa.Column("u_height", sa.SmallInteger(), nullable=False),
        sa.Column("face", RACK_FACE, server_default="FRONT", nullable=False),
        sa.Column("zero_u_side", ZERO_U, nullable=True),
        sa.Column("depth_mm", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column("is_reservation", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "u_range",
            postgresql.INT4RANGE(),
            sa.Computed("int4range(position_u, position_u + u_height)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "occupies_front",
            sa.Boolean(),
            sa.Computed("((face IN ('FRONT', 'FULL')) AND (u_height > 0))", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "occupies_rear",
            sa.Boolean(),
            sa.Computed("((face IN ('REAR', 'FULL')) AND (u_height > 0))", persisted=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position_u >= 1", name=op.f("ck_rack_mount_position_u")),
        sa.CheckConstraint("u_height >= 0 AND u_height <= 60", name=op.f("ck_rack_mount_u_height")),
        sa.CheckConstraint(
            "(u_height = 0 AND zero_u_side IS NOT NULL) OR (u_height > 0 AND zero_u_side IS NULL)",
            name=op.f("ck_rack_mount_zero_u"),
        ),
        sa.ForeignKeyConstraint(
            ["ci_id"], ["ci.id"], name=op.f("fk_rack_mount_ci_id_ci"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rack_id"], ["rack.id"], name=op.f("fk_rack_mount_rack_id_rack"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rack_mount")),
        sa.UniqueConstraint("ci_id", name="uq_rack_mount_ci_id"),
    )
    op.execute(
        """
        ALTER TABLE rack_mount ADD CONSTRAINT ex_rack_mount_front
        EXCLUDE USING gist (rack_id WITH =, u_range WITH &&)
        WHERE (occupies_front AND NOT is_reservation)
        """
    )
    op.execute(
        """
        ALTER TABLE rack_mount ADD CONSTRAINT ex_rack_mount_rear
        EXCLUDE USING gist (rack_id WITH =, u_range WITH &&)
        WHERE (occupies_rear AND NOT is_reservation)
        """
    )
    op.execute(
        """
        CREATE FUNCTION rack_mount_within_rack() RETURNS trigger AS $$
        DECLARE
          rack_u smallint;
        BEGIN
          IF NEW.u_height = 0 THEN
            RETURN NEW;
          END IF;
          SELECT u_height INTO rack_u FROM rack WHERE id = NEW.rack_id;
          IF NEW.position_u + NEW.u_height - 1 > rack_u THEN
            RAISE EXCEPTION 'mount_out_of_rack'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_rack_mount_within_rack
        BEFORE INSERT OR UPDATE ON rack_mount
        FOR EACH ROW EXECUTE FUNCTION rack_mount_within_rack()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_rack_mount_within_rack ON rack_mount")
    op.execute("DROP FUNCTION IF EXISTS rack_mount_within_rack()")
    op.drop_table("rack_mount")
    op.drop_table("rack")
    op.execute("DROP TYPE IF EXISTS zero_u_side")
    op.execute("DROP TYPE IF EXISTS rack_face")
    op.execute("DROP TYPE IF EXISTS rack_form_factor")
