from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import DocumentKind, DocumentStatus


class DocumentLinkWrite(BaseModel):
    entity_type: str = Field(max_length=64)
    entity_id: uuid.UUID
    relation: str | None = None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    kind: DocumentKind = DocumentKind.NOTE
    summary: str | None = None
    folder_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    review_period_days: int | None = Field(default=None, ge=1, le=3650)
    content: str = ""
    content_format: str = Field(default="markdown", pattern="^(markdown|html|plain)$")
    links: list[DocumentLinkWrite] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    title: str | None = None
    kind: DocumentKind | None = None
    status: DocumentStatus | None = None
    summary: str | None = None
    folder_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None
    review_period_days: int | None = None
    content: str | None = None
    content_format: str | None = None
    change_note: str | None = None


class DocumentRead(ORMModel):
    id: uuid.UUID
    title: str
    kind: DocumentKind
    status: DocumentStatus
    summary: str | None
    folder_id: uuid.UUID | None
    owner_employee_id: uuid.UUID | None
    current_version: int
    reviewed_on: date | None
    review_due_on: date | None
    review_period_days: int | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    content: str | None = None
    content_format: str | None = None
    links: list[DocumentLinkRead] = Field(default_factory=list)


class DocumentLinkRead(ORMModel):
    id: uuid.UUID
    document_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    relation: str | None


DocumentDetail.model_rebuild()


class DocumentVersionRead(ORMModel):
    id: uuid.UUID
    version: int
    title: str
    content_format: str
    change_note: str | None
    created_at: datetime
    created_by: uuid.UUID | None
    is_current: bool


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    description: str | None = None


class FolderRead(ORMModel):
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    path: str
    description: str | None


class FileRead(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    download_url: str | None = None


class AttachmentRead(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    title: str | None
    created_at: datetime
