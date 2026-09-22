"""Узлы питания, ветки, замеры, связи и прогноз нагрузки

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22 20:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NODE_TYPE = postgresql.ENUM(
    "INPUT",
    "PANEL",
    "BREAKER",
    "LINE",
    "TRANSFER_SWITCH",
    "UPS",
    "PDU",
    "OUTLET",
    "PSU",
    "GENERIC_LOAD",
    name="power_node_type",
    create_type=False,
)
FEED_SIDE = postgresql.ENUM("A", "B", "SINGLE", name="feed_side", create_type=False)
PHASE = postgresql.ENUM("L1", "L2", "L3", "L1L2L3", name="phase_label", create_type=False)
CONNECTION = postgresql.ENUM(
    "PLANNED",
    "RESERVED",
    "ACTIVE",
    "FAULTY",
    "DECOMMISSIONED",
    name="connection_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE power_node_type AS ENUM ("
        "'INPUT', 'PANEL', 'BREAKER', 'LINE', 'TRANSFER_SWITCH', "
        "'UPS', 'PDU', 'OUTLET', 'PSU', 'GENERIC_LOAD')"
    )
    op.execute("CREATE TYPE feed_side AS ENUM ('A', 'B', 'SINGLE')")
    op.execute("CREATE TYPE phase_label AS ENUM ('L1', 'L2', 'L3', 'L1L2L3')")

    op.create_table(
        "power_node",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("node_type", NODE_TYPE, nullable=False),
        sa.Column("parent_device_id", sa.UUID(), nullable=True),
        sa.Column("rack_id", sa.UUID(), nullable=True),
        sa.Column("feed_side", FEED_SIDE, server_default="SINGLE", nullable=False),
        sa.Column("voltage_v", sa.Numeric(6, 1), nullable=True),
        sa.Column("phases", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("phase_label", PHASE, nullable=True),
        sa.Column("rated_current_a", sa.Numeric(7, 2), nullable=True),
        sa.Column("breaker_curve", sa.String(8), nullable=True),
        sa.Column("breaker_poles", sa.String(8), nullable=True),
        sa.Column("cable_spec", sa.Text(), nullable=True),
        sa.Column("cable_length_m", sa.Numeric(6, 2), nullable=True),
        sa.Column("cable_ampacity_a", sa.Numeric(7, 2), nullable=True),
        sa.Column("derating_factor", sa.Numeric(4, 3), server_default=sa.text("0.8"), nullable=False),
        sa.Column("power_factor", sa.Numeric(4, 3), nullable=True),
        sa.Column("efficiency", sa.Numeric(4, 3), nullable=True),
        sa.Column("power_nameplate_w", sa.Integer(), nullable=True),
        sa.Column("power_max_w", sa.Integer(), nullable=True),
        sa.Column("max_load_w", sa.Integer(), nullable=True),
        sa.Column("ups_capacity_va", sa.Integer(), nullable=True),
        sa.Column("ups_capacity_w", sa.Integer(), nullable=True),
        sa.Column("ups_battery_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("outlet_type", sa.String(32), nullable=True),
        sa.Column("outlet_count", sa.SmallInteger(), nullable=True),
        sa.Column("utilization", sa.Numeric(4, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("phases IN (1, 3)", name="ck_power_node_phases"),
        sa.CheckConstraint(
            "phases <> 1 OR node_type IN ('INPUT', 'PANEL') OR phase_label IS NOT NULL",
            name="ck_power_node_single_phase_label",
        ),
        sa.CheckConstraint(
            "breaker_curve IS NULL OR breaker_curve IN ('B', 'C', 'D')",
            name="ck_power_node_breaker_curve",
        ),
        sa.CheckConstraint(
            "breaker_poles IS NULL OR breaker_poles IN ('1P', '1P+N', '3P', '3P+N')",
            name="ck_power_node_breaker_poles",
        ),
        sa.ForeignKeyConstraint(["id"], ["ci.id"], name=op.f("fk_power_node_id_ci"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_device_id"], ["ci.id"],
            name=op.f("fk_power_node_parent_device_id_ci"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rack_id"], ["rack.id"],
            name=op.f("fk_power_node_rack_id_rack"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_node")),
    )
    op.create_index("ix_power_node_node_type", "power_node", ["node_type"])
    op.create_index("ix_power_node_rack_id", "power_node", ["rack_id"])

    op.create_table(
        "power_feed",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("side", FEED_SIDE, nullable=False),
        sa.Column("root_node_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("is_protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["root_node_id"], ["power_node.id"],
            name=op.f("fk_power_feed_root_node_id_power_node"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["location.id"],
            name=op.f("fk_power_feed_location_id_location"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_feed")),
        sa.UniqueConstraint("location_id", "name", name="uq_power_feed_location_name"),
    )
    op.add_column("power_node", sa.Column("feed_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_power_node_feed_id_power_feed",
        "power_node",
        "power_feed",
        ["feed_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_power_node_feed_id", "power_node", ["feed_id"])

    op.create_table(
        "power_measurement",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("power_w", sa.Integer(), nullable=True),
        sa.Column("current_a", sa.Numeric(7, 2), nullable=True),
        sa.Column("voltage_v", sa.Numeric(6, 1), nullable=True),
        sa.Column("power_factor", sa.Numeric(4, 3), nullable=True),
        sa.Column("phase_label", PHASE, nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("measured_by", sa.UUID(), nullable=True),
        sa.Column("instrument", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("is_peak", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "source IN ('MANUAL', 'PDU', 'UPS', 'METER', 'IMPORT', 'MONITORING')",
            name="ck_power_measurement_source",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["power_node.id"],
            name=op.f("fk_power_measurement_node_id_power_node"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["measured_by"], ["employee.id"],
            name=op.f("fk_power_measurement_measured_by_employee"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_measurement")),
    )
    op.create_index("ix_power_measurement_node_id", "power_measurement", ["node_id"])
    op.create_index(
        "ix_power_measurement_node_time",
        "power_measurement",
        ["node_id", sa.text("measured_at DESC")],
    )

    op.create_table(
        "power_link",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("phase_label", PHASE, nullable=True),
        sa.Column("rated_current_a", sa.Numeric(7, 2), nullable=True),
        sa.Column("cable_spec", sa.Text(), nullable=True),
        sa.Column("length_m", sa.Numeric(6, 2), nullable=True),
        sa.Column("status", CONNECTION, server_default="ACTIVE", nullable=False),
        sa.Column("outlet_number", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "source_node_id <> target_node_id", name="ck_power_link_distinct"
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["power_node.id"],
            name=op.f("fk_power_link_source_node_id_power_node"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"], ["power_node.id"],
            name=op.f("fk_power_link_target_node_id_power_node"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_link")),
        sa.UniqueConstraint("source_node_id", "target_node_id", name="uq_power_link_pair"),
    )
    op.create_index("ix_power_link_source_node_id", "power_link", ["source_node_id"])
    op.create_index("ix_power_link_target_node_id", "power_link", ["target_node_id"])

    op.create_table(
        "power_scenario",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("charge_w", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ups_efficiency", sa.Numeric(4, 3), nullable=True),
        sa.Column("reserve", sa.Numeric(4, 3), server_default=sa.text("0.20"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"],
            name=op.f("fk_power_scenario_project_id_project"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_scenario")),
    )
    op.create_table(
        "power_scenario_item",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("scenario_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("nameplate_w", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("utilization", sa.Numeric(4, 3), nullable=False),
        sa.Column("behind_new_ups", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["power_scenario.id"],
            name=op.f("fk_power_scenario_item_scenario_id_power_scenario"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_power_scenario_item")),
    )
    op.create_index(
        "ix_power_scenario_item_scenario_id", "power_scenario_item", ["scenario_id"]
    )


def downgrade() -> None:
    op.drop_table("power_scenario_item")
    op.drop_table("power_scenario")
    op.drop_table("power_link")
    op.drop_table("power_measurement")
    op.drop_constraint("fk_power_node_feed_id_power_feed", "power_node", type_="foreignkey")
    op.drop_index("ix_power_node_feed_id", table_name="power_node")
    op.drop_column("power_node", "feed_id")
    op.drop_table("power_feed")
    op.drop_table("power_node")
    op.execute("DROP TYPE phase_label")
    op.execute("DROP TYPE feed_side")
    op.execute("DROP TYPE power_node_type")
