from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import ActorMixin, Base, LifecycleMixin, TimestampMixin, uuid_pk
from itms.models.enums import DocumentKind, DocumentStatus


class DocumentFolder(Base, TimestampMixin, ActorMixin):
    __tablename__ = "document_folder"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_folder.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text)


class FileObject(Base, TimestampMixin):
    """Файл в объектном хранилище.

    Содержимое адресуется хешем: повторная загрузка того же файла не дублирует данные.
    """

    __tablename__ = "file_object"
    __table_args__ = (Index("ix_file_object_sha256", "sha256"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )


class Document(Base, TimestampMixin, ActorMixin, LifecycleMixin):
    """Документ базы знаний. Текущее содержимое — последняя версия в document_version."""

    __tablename__ = "document"
    __table_args__ = (
        Index("ix_document_status", "status"),
        Index("ix_document_review", "review_due_on"),
        Index("ix_document_search", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_folder.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(
        ENUM(DocumentKind, name="document_kind", create_type=False),
        nullable=False,
        default=DocumentKind.NOTE,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        ENUM(DocumentStatus, name="document_status", create_type=False),
        nullable=False,
        default=DocumentStatus.DRAFT,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_on: Mapped[date | None] = mapped_column(Date)
    review_due_on: Mapped[date | None] = mapped_column(Date)
    review_period_days: Mapped[int | None] = mapped_column(Integer)
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", lazy="noload", order_by="DocumentVersion.version.desc()"
    )


class DocumentVersion(Base):
    """Неизменяемая версия документа: правка создаёт новую запись, старая сохраняется."""

    __tablename__ = "document_version"
    __table_args__ = (UniqueConstraint("document_id", "version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_format: Mapped[str] = mapped_column(String(16), nullable=False, default="markdown")
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_object.id", ondelete="SET NULL")
    )
    change_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    document: Mapped[Document] = relationship(back_populates="versions", lazy="noload")
    file: Mapped[FileObject | None] = relationship(lazy="joined")


class DocumentLink(Base, TimestampMixin):
    """Связь документа с любой сущностью системы: объектом, локацией, проектом."""

    __tablename__ = "document_link"
    __table_args__ = (
        UniqueConstraint("document_id", "entity_type", "entity_id"),
        Index("ix_document_link_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    relation: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )


class Attachment(Base, TimestampMixin):
    """Файл, прикреплённый к произвольной сущности."""

    __tablename__ = "attachment"
    __table_args__ = (Index("ix_attachment_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("file_object.id", ondelete="RESTRICT"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )

    file: Mapped[FileObject] = relationship(lazy="joined")
