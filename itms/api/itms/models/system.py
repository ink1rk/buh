from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, TimestampMixin, uuid_pk
from itms.models.enums import ImportStatus, ImportTarget


class AppSetting(Base, TimestampMixin):
    """Настройки установки, включая значения по умолчанию для электрических расчётов."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    description: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )


class OutboxEvent(Base):
    """Доменное событие для асинхронной обработки: запись в той же транзакции, что и данные."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        Index("ix_outbox_pending", "created_at", postgresql_where=text("processed_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ImportJob(Base, TimestampMixin):
    """Импорт CSV/XLSX: загрузка → маппинг колонок → проверка → применение."""

    __tablename__ = "import_job"

    id: Mapped[uuid.UUID] = uuid_pk()
    target: Mapped[ImportTarget] = mapped_column(
        ENUM(ImportTarget, name="import_target", create_type=False), nullable=False
    )
    status: Mapped[ImportStatus] = mapped_column(
        ENUM(ImportStatus, name="import_status", create_type=False),
        nullable=False,
        default=ImportStatus.DRAFT,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_object.id", ondelete="SET NULL")
    )
    #: Соответствие «колонка файла → поле сущности», задаётся пользователем.
    mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    preview: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
