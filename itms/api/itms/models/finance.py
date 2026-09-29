"""Бюджет отдела и бюджет движения денежных средств."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import ActorMixin, Base, TimestampMixin, uuid_pk


class FinanceEntry(Base, TimestampMixin, ActorMixin):
    __tablename__ = "finance_entry"
    __table_args__ = (
        CheckConstraint("kind IN ('BUDGET', 'CASHFLOW')", name="kind"),
        CheckConstraint("direction IN ('IN', 'OUT')", name="direction"),
        Index("ix_finance_entry_period", "kind", "period"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    article: Mapped[str] = mapped_column(String(255), nullable=False)
    planned: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    actual: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
