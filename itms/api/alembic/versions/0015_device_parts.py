"""Платформа модели и комплектующие устройства

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-28 16:40:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
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
    op.add_column(
        "device_model",
        sa.Column("component_class", sa.String(16), nullable=False, server_default="CHASSIS"),
    )
    op.add_column("device_model", sa.Column("cpu_sockets", sa.SmallInteger(), nullable=True))
    op.add_column("device_model", sa.Column("cpu_socket", sa.String(32), nullable=True))
    op.add_column("device_model", sa.Column("ram_slots", sa.SmallInteger(), nullable=True))
    op.add_column("device_model", sa.Column("ram_type", sa.String(16), nullable=True))
    op.add_column("device_model", sa.Column("drive_bays", sa.SmallInteger(), nullable=True))
    op.add_column("device_model", sa.Column("drive_form", sa.String(32), nullable=True))
    op.create_check_constraint(
        op.f("ck_device_model_component_class"),
        "device_model",
        "component_class IN ('CHASSIS','BOARD','CPU','MEMORY','DISK','NIC','HBA','PSU')",
    )
    op.create_table(
        "device_part",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
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
        sa.CheckConstraint("quantity >= 1", name=op.f("ck_device_part_quantity")),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["device.id"],
            name=op.f("fk_device_part_device_id_device"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_model_id"],
            ["device_model.id"],
            name=op.f("fk_device_part_component_model_id_device_model"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_part")),
        sa.UniqueConstraint(
            "device_id",
            "component_model_id",
            name=op.f("uq_device_part_device_id_component_model_id"),
        ),
    )
    _actor_keys("device_part", create=True)


def downgrade() -> None:
    _actor_keys("device_part", create=False)
    op.drop_table("device_part")
    op.drop_constraint(op.f("ck_device_model_component_class"), "device_model", type_="check")
    for column in (
        "drive_form",
        "drive_bays",
        "ram_type",
        "ram_slots",
        "cpu_socket",
        "cpu_sockets",
        "component_class",
    ):
        op.drop_column("device_model", column)
