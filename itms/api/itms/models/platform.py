"""Платформа проекта: кластер Kubernetes, MCP, агент и маршрут сервиса.

Записи живут рядом с проектами. VLAN и виртуальные машины остаются в своих
таблицах, маршрут только ссылается на них.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import ActorMixin, Base, TimestampMixin, uuid_pk


class K8sCluster(Base, TimestampMixin, ActorMixin):
    __tablename__ = "k8s_cluster"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('PROD', 'STAGE', 'DEV', 'OTHER')",
            name="environment",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="PROD")
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL")
    )
    host_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compute_host.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class McpServer(Base, TimestampMixin, ActorMixin):
    __tablename__ = "mcp_server"
    __table_args__ = (
        CheckConstraint("transport IN ('HTTP', 'SSE', 'STDIO')", name="transport"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="HTTP")
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("k8s_cluster.id", ondelete="SET NULL")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)


class AgentService(Base, TimestampMixin, ActorMixin):
    __tablename__ = "agent_service"
    __table_args__ = (CheckConstraint("kind IN ('OPENCODE', 'OTHER')", name="kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="OPENCODE")
    endpoint: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str | None] = mapped_column(String(128))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)


class AgentMcp(Base):
    __tablename__ = "agent_mcp"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_service.id", ondelete="CASCADE"), primary_key=True
    )
    mcp_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mcp_server.id", ondelete="CASCADE"), primary_key=True
    )


class ServiceRoute(Base, TimestampMixin, ActorMixin):
    __tablename__ = "service_route"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('CLUSTER', 'MCP', 'AGENT', 'VM', 'URL')",
            name="target_kind",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, default="/")
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    target_url: Mapped[str | None] = mapped_column(String(500))
    vlan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vlan.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
