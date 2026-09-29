"""Хосты виртуализации и ресурсы виртуальных машин

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-23 16:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = postgresql.ENUM(
    "PROXMOX",
    "VMWARE",
    "HYPERV",
    "KVM",
    "OTHER",
    name="hypervisor_platform",
    create_type=False,
)
POWER_STATE = postgresql.ENUM(
    "RUNNING",
    "STOPPED",
    "SUSPENDED",
    name="vm_power_state",
    create_type=False,
)


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
    op.execute(
        "CREATE TYPE hypervisor_platform AS ENUM "
        "('PROXMOX', 'VMWARE', 'HYPERV', 'KVM', 'OTHER')"
    )
    op.execute("CREATE TYPE vm_power_state AS ENUM ('RUNNING', 'STOPPED', 'SUSPENDED')")
    op.create_table(
        "compute_host",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", PLATFORM, nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("memory_mb", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("storage_gb", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("cpu_cores >= 0", name=op.f("ck_compute_host_cpu_cores")),
        sa.CheckConstraint("memory_mb >= 0", name=op.f("ck_compute_host_memory_mb")),
        sa.CheckConstraint("storage_gb >= 0", name=op.f("ck_compute_host_storage_gb")),
        sa.ForeignKeyConstraint(
            ["id"], ["ci.id"], name=op.f("fk_compute_host_id_ci"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compute_host")),
    )
    op.create_table(
        "virtual_machine",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vcpu", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("disk_gb", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("guest_os", sa.String(128), nullable=True),
        sa.Column("power_state", POWER_STATE, nullable=False, server_default="RUNNING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("vcpu >= 1", name=op.f("ck_virtual_machine_vcpu")),
        sa.CheckConstraint("memory_mb >= 1", name=op.f("ck_virtual_machine_memory_mb")),
        sa.CheckConstraint("disk_gb >= 0", name=op.f("ck_virtual_machine_disk_gb")),
        sa.ForeignKeyConstraint(
            ["id"], ["ci.id"], name=op.f("fk_virtual_machine_id_ci"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["compute_host.id"],
            name=op.f("fk_virtual_machine_host_id_compute_host"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_virtual_machine")),
    )
    op.create_index("ix_virtual_machine_host_id", "virtual_machine", ["host_id"])
    _actor_keys("compute_host", create=True)
    _actor_keys("virtual_machine", create=True)


def downgrade() -> None:
    _actor_keys("virtual_machine", create=False)
    _actor_keys("compute_host", create=False)
    op.drop_index("ix_virtual_machine_host_id", table_name="virtual_machine")
    op.drop_table("virtual_machine")
    op.drop_table("compute_host")
    op.execute("DROP TYPE vm_power_state")
    op.execute("DROP TYPE hypervisor_platform")
