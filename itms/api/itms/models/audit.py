from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import Base, uuid_pk
from itms.models.enums import AuditAction


class AuditLog(Base):
    """Неизменяемая запись о действии.

    Помимо «кто и когда» фиксирует происхождение изменения: в рамках какого проекта,
    изменения, задачи или документа оно выполнено и по какой причине.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_audit_log_occurred", "occurred_at"),
        Index("ix_audit_log_actor", "actor_id"),
        Index("ix_audit_log_change", "change_id", postgresql_where=text("change_id IS NOT NULL")),
        Index("ix_audit_log_project", "project_id",
              postgresql_where=text("project_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="USER")
    actor_label: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    entity_label: Mapped[str | None] = mapped_column(String(500))
    action: Mapped[AuditAction] = mapped_column(
        ENUM(AuditAction, name="audit_action", create_type=False), nullable=False
    )
    # Происхождение изменения
    change_id: Mapped[uuid.UUID | None] = mapped_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column()
    task_id: Mapped[uuid.UUID | None] = mapped_column()
    document_id: Mapped[uuid.UUID | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="api")
    ip: Mapped[str | None] = mapped_column(String(64))
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    changes: Mapped[list[AuditChange]] = relationship(
        back_populates="log", lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def has_provenance(self) -> bool:
        return any((self.change_id, self.project_id, self.task_id, self.document_id, self.reason))


class AuditChange(Base):
    """Изменение конкретного поля: было → стало."""

    __tablename__ = "audit_change"
    __table_args__ = (Index("ix_audit_change_field", "field"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    audit_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_log.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)

    log: Mapped[AuditLog] = relationship(back_populates="changes", lazy="noload")
