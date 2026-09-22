"""Схемы: раскладка узлов и ссылки рёбер на кабели и связи

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22 14:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIAGRAM_TYPE = postgresql.ENUM(
    "NETWORK", "LOGICAL", name="diagram_type", create_type=False
)
NODE_KIND = postgresql.ENUM(
    "CI", "GROUP", "NOTE", "CLOUD", name="diagram_node_kind", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE TYPE diagram_type AS ENUM ('NETWORK', 'LOGICAL')")
    op.execute("CREATE TYPE diagram_node_kind AS ENUM ('CI', 'GROUP', 'NOTE', 'CLOUD')")

    op.create_table(
        "diagram",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("diagram_type", DIAGRAM_TYPE, nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("viewport", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"], ["location.id"],
            name=op.f("fk_diagram_location_id_location"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagram")),
    )
    op.create_table(
        "diagram_node",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("diagram_id", sa.UUID(), nullable=False),
        sa.Column("ci_id", sa.UUID(), nullable=True),
        sa.Column("node_kind", NODE_KIND, nullable=False),
        sa.Column("x", sa.Numeric(10, 2), nullable=False),
        sa.Column("y", sa.Numeric(10, 2), nullable=False),
        sa.Column("width", sa.Numeric(10, 2), nullable=True),
        sa.Column("height", sa.Numeric(10, 2), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("collapsed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ci_id"], ["ci.id"], name=op.f("fk_diagram_node_ci_id_ci"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diagram_id"], ["diagram.id"],
            name=op.f("fk_diagram_node_diagram_id_diagram"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagram_node")),
        sa.UniqueConstraint("diagram_id", "ci_id", name="uq_diagram_node_ci"),
    )
    op.create_table(
        "diagram_edge",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("diagram_id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=True),
        sa.Column("relation_id", sa.UUID(), nullable=True),
        sa.Column("source_node_id", sa.UUID(), nullable=False),
        sa.Column("target_node_id", sa.UUID(), nullable=False),
        sa.Column("waypoints", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(connection_id, relation_id) <= 1",
            name=op.f("ck_diagram_edge_one_backing"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["connection.id"],
            name=op.f("fk_diagram_edge_connection_id_connection"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diagram_id"], ["diagram.id"],
            name=op.f("fk_diagram_edge_diagram_id_diagram"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["relation_id"], ["ci_relation.id"],
            name=op.f("fk_diagram_edge_relation_id_ci_relation"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["diagram_node.id"],
            name=op.f("fk_diagram_edge_source_node_id_diagram_node"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"], ["diagram_node.id"],
            name=op.f("fk_diagram_edge_target_node_id_diagram_node"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagram_edge")),
    )


def downgrade() -> None:
    op.drop_table("diagram_edge")
    op.drop_table("diagram_node")
    op.drop_table("diagram")
    op.execute("DROP TYPE IF EXISTS diagram_node_kind")
    op.execute("DROP TYPE IF EXISTS diagram_type")
