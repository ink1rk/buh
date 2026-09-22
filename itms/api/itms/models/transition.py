"""Снимок модели и план её изменения. До применения рабочая модель не трогается."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, uuid_pk


class StateSnapshot(Base):
    """Неизменяемый срез. Новая дата — новая строка, старая не переписывается."""

    __tablename__ = "state_snapshot"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    taken_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )


class PlannedChange(Base):
    """Целевое состояние проекта. Статус APPLIED значит, что модель уже обновлена."""

    __tablename__ = "planned_change"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEW', 'APPROVED', 'APPLYING', 'APPLIED', 'CANCELLED')",
            name="ck_planned_change_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id", ondelete="SET NULL")
    )
    result_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeItem(Base):
    """Одна операция плана. before хранит прежние значения для отката."""

    __tablename__ = "change_item"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('CREATE', 'UPDATE', 'DELETE', 'MOVE', 'CONNECT', 'DISCONNECT')",
            name="ck_change_item_operation",
        ),
        CheckConstraint(
            "apply_status IN ('PENDING', 'APPLIED', 'SKIPPED', 'FAILED')",
            name="ck_change_item_apply_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    planned_change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("planned_change.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    apply_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    applied_entity_id: Mapped[uuid.UUID | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
