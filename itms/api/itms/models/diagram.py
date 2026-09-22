"""Схемы: хранится только раскладка. Имена, статусы и кабели читаются из модели."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import Base, TimestampMixin, VersionMixin, uuid_pk
from itms.models.enums import DiagramNodeKind, DiagramType


class Diagram(Base, TimestampMixin, VersionMixin):
    __tablename__ = "diagram"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    diagram_type: Mapped[DiagramType] = mapped_column(
        ENUM(DiagramType, name="diagram_type", create_type=False),
        nullable=False,
        default=DiagramType.NETWORK,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    viewport: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    nodes: Mapped[list[DiagramNode]] = relationship(
        back_populates="diagram", cascade="all, delete-orphan", lazy="noload"
    )


class DiagramNode(Base, TimestampMixin):
    __tablename__ = "diagram_node"
    __table_args__ = (
        UniqueConstraint("diagram_id", "ci_id", name="uq_diagram_node_ci"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    diagram_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False
    )
    ci_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ci.id", ondelete="CASCADE"))
    node_kind: Mapped[DiagramNodeKind] = mapped_column(
        ENUM(DiagramNodeKind, name="diagram_node_kind", create_type=False),
        nullable=False,
        default=DiagramNodeKind.CI,
    )
    x: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    y: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    width: Mapped[float | None] = mapped_column(Numeric(10, 2))
    height: Mapped[float | None] = mapped_column(Numeric(10, 2))
    label: Mapped[str | None] = mapped_column(String(255))
    collapsed: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )

    diagram: Mapped[Diagram] = relationship(back_populates="nodes")


class DiagramEdge(Base, TimestampMixin):
    """Ребро ссылается на кабель или логическую связь. Свойства линии не копируются."""

    __tablename__ = "diagram_edge"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(connection_id, relation_id) <= 1",
            name="one_backing",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    diagram_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connection.id", ondelete="CASCADE")
    )
    relation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ci_relation.id", ondelete="CASCADE")
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram_node.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagram_node.id", ondelete="CASCADE"), nullable=False
    )
    waypoints: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
