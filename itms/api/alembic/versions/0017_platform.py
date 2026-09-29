"""Кластеры Kubernetes, MCP, агенты и маршруты сервисов

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-28 18:40:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
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


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "k8s_cluster",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("environment", sa.String(16), nullable=False, server_default="PROD"),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "environment IN ('PROD', 'STAGE', 'DEV', 'OTHER')",
            name=op.f("ck_k8s_cluster_environment"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_k8s_cluster_project_id_project"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["compute_host.id"],
            name=op.f("fk_k8s_cluster_host_id_compute_host"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_k8s_cluster")),
    )
    op.create_table(
        "mcp_server",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False, server_default="HTTP"),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "transport IN ('HTTP', 'SSE', 'STDIO')",
            name=op.f("ck_mcp_server_transport"),
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["k8s_cluster.id"],
            name=op.f("fk_mcp_server_cluster_id_k8s_cluster"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_mcp_server_project_id_project"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_server")),
    )
    op.create_table(
        "agent_service",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="OPENCODE"),
        sa.Column("endpoint", sa.String(500), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('OPENCODE', 'OTHER')",
            name=op.f("ck_agent_service_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_agent_service_project_id_project"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_service")),
    )
    op.create_table(
        "agent_mcp",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agent_service.id"],
            name=op.f("fk_agent_mcp_agent_id_agent_service"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mcp_id"],
            ["mcp_server.id"],
            name=op.f("fk_agent_mcp_mcp_id_mcp_server"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("agent_id", "mcp_id", name=op.f("pk_agent_mcp")),
    )
    op.create_table(
        "service_route",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("path", sa.String(255), nullable=False, server_default="/"),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_url", sa.String(500), nullable=True),
        sa.Column("vlan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "target_kind IN ('CLUSTER', 'MCP', 'AGENT', 'VM', 'URL')",
            name=op.f("ck_service_route_target_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["vlan_id"], ["vlan.id"], name=op.f("fk_service_route_vlan_id_vlan"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_service_route_project_id_project"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_route")),
    )
    for table in ("k8s_cluster", "mcp_server", "agent_service", "service_route"):
        _actor_keys(table, create=True)


def downgrade() -> None:
    for table in ("service_route", "agent_service", "mcp_server", "k8s_cluster"):
        _actor_keys(table, create=False)
    op.drop_table("service_route")
    op.drop_table("agent_mcp")
    op.drop_table("agent_service")
    op.drop_table("mcp_server")
    op.drop_table("k8s_cluster")
