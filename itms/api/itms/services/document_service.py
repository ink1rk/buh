from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.context import current_context
from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.locations import PATH_SEPARATOR, build_path
from itms.domain.search import document_document
from itms.models.documents import Document, DocumentFolder, DocumentLink, DocumentVersion
from itms.models.enums import DocumentStatus
from itms.services import search_service

DOCUMENT_FIELDS = ("title", "kind", "summary", "folder_id", "owner_employee_id",
                   "review_period_days")

#: Из какого статуса в какой можно перевести документ.
STATUS_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.DRAFT: frozenset({DocumentStatus.IN_REVIEW, DocumentStatus.APPROVED,
                                     DocumentStatus.ARCHIVED}),
    DocumentStatus.IN_REVIEW: frozenset({DocumentStatus.DRAFT, DocumentStatus.APPROVED,
                                         DocumentStatus.ARCHIVED}),
    DocumentStatus.APPROVED: frozenset({DocumentStatus.IN_REVIEW, DocumentStatus.OBSOLETE,
                                        DocumentStatus.ARCHIVED}),
    DocumentStatus.OBSOLETE: frozenset({DocumentStatus.ARCHIVED, DocumentStatus.IN_REVIEW}),
    DocumentStatus.ARCHIVED: frozenset({DocumentStatus.DRAFT}),
}


async def refresh_document(session: AsyncSession, doc: Document) -> Document:
    """После записи значения, проставленные базой, нужно перечитать явно."""
    await session.refresh(doc)
    return doc


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if doc is None:
        raise NotFound("Документ не найден", entity_id=str(document_id))
    return doc


async def current_content(session: AsyncSession, document_id: uuid.UUID) -> DocumentVersion | None:
    return (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id, DocumentVersion.is_current.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    *,
    q: str | None = None,
    status: list[DocumentStatus] | None = None,
    folder_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    review_due: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if q:
        stmt = stmt.where(func.lower(Document.title).like(f"%{q.lower()}%"))
    if status:
        stmt = stmt.where(Document.status.in_(status))
    if folder_id:
        stmt = stmt.where(Document.folder_id == folder_id)
    if entity_type and entity_id:
        stmt = stmt.where(
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.entity_type == entity_type,
                    DocumentLink.entity_id == entity_id,
                )
            )
        )
    if review_due:
        stmt = stmt.where(
            Document.review_due_on.isnot(None), Document.review_due_on <= date.today()
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = await session.execute(
        stmt.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().unique()), int(total)


async def create_document(session: AsyncSession, data: dict[str, Any]) -> Document:
    doc = Document(
        title=data["title"],
        **{k: v for k, v in data.items() if k in DOCUMENT_FIELDS and k != "title"},
    )
    session.add(doc)
    await session.flush()
    await add_version(
        session,
        doc,
        content=data.get("content", ""),
        content_format=data.get("content_format", "markdown"),
        change_note="Создание документа",
    )
    for link in data.get("links", []) or []:
        await link_document(session, doc.id, link["entity_type"], link["entity_id"],
                            link.get("relation"))
    return await refresh_document(session, doc)


async def update_document(
    session: AsyncSession, document_id: uuid.UUID, data: dict[str, Any]
) -> Document:
    doc = await get_document(session, document_id)
    if "status" in data and data["status"] is not None:
        await set_status(session, doc, DocumentStatus(data["status"]))
    for key in DOCUMENT_FIELDS:
        if key in data:
            setattr(doc, key, data[key])
    if "content" in data and data["content"] is not None:
        await add_version(
            session,
            doc,
            content=data["content"],
            content_format=data.get("content_format", "markdown"),
            change_note=data.get("change_note"),
        )
    await session.flush()
    await _reindex(session, doc)
    return await refresh_document(session, doc)


async def set_status(session: AsyncSession, doc: Document, target: DocumentStatus) -> None:
    if doc.status == target:
        return
    allowed = STATUS_TRANSITIONS.get(doc.status, frozenset())
    if target not in allowed:
        raise Invalid(
            f"Переход статуса документа {doc.status.value} → {target.value} не разрешён",
            code_hint="invalid_status_transition",
            allowed=sorted(s.value for s in allowed),
        )
    doc.status = target
    if target == DocumentStatus.APPROVED:
        doc.reviewed_on = date.today()
        if doc.review_period_days:
            doc.review_due_on = date.today() + timedelta(days=doc.review_period_days)


async def add_version(
    session: AsyncSession,
    doc: Document,
    *,
    content: str,
    content_format: str = "markdown",
    change_note: str | None = None,
    file_id: uuid.UUID | None = None,
) -> DocumentVersion:
    """Новая версия не затирает предыдущую: история содержимого сохраняется целиком."""
    previous = await current_content(session, doc.id)
    if previous is not None:
        if previous.content == content and previous.file_id == file_id:
            return previous
        previous.is_current = False
    version = DocumentVersion(
        document_id=doc.id,
        version=doc.current_version + 1,
        title=doc.title,
        content=content or "",
        content_format=content_format,
        file_id=file_id,
        change_note=change_note,
        created_by=current_context().actor_id,
        is_current=True,
    )
    session.add(version)
    doc.current_version = version.version
    await session.flush()
    await _reindex(session, doc, content)
    return version


async def list_versions(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentVersion]:
    rows = await session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
    )
    return list(rows.scalars().unique())


async def restore_version(
    session: AsyncSession, document_id: uuid.UUID, version: int
) -> DocumentVersion:
    doc = await get_document(session, document_id)
    source = (
        await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id, DocumentVersion.version == version
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise NotFound("Версия документа не найдена", version=version)
    return await add_version(
        session,
        doc,
        content=source.content,
        content_format=source.content_format,
        change_note=f"Возврат к версии {version}",
        file_id=source.file_id,
    )


async def link_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    relation: str | None = None,
) -> DocumentLink:
    exists = (
        await session.execute(
            select(DocumentLink.id).where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type == entity_type,
                DocumentLink.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise Conflict("Документ уже связан с этим объектом")
    link = DocumentLink(
        document_id=document_id,
        entity_type=entity_type,
        entity_id=entity_id,
        relation=relation,
        created_by=current_context().actor_id,
    )
    session.add(link)
    await session.flush()
    return link


async def unlink_document(session: AsyncSession, link_id: uuid.UUID) -> None:
    link = (
        await session.execute(select(DocumentLink).where(DocumentLink.id == link_id))
    ).scalar_one_or_none()
    if link is None:
        raise NotFound("Связь документа не найдена")
    await session.delete(link)
    await session.flush()


async def links_of(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentLink]:
    rows = await session.execute(
        select(DocumentLink).where(DocumentLink.document_id == document_id)
    )
    return list(rows.scalars().unique())


async def archive_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = await get_document(session, document_id)
    doc.archived_at = datetime.now(UTC)
    doc.status = DocumentStatus.ARCHIVED
    await session.flush()
    await search_service.remove_entity(session, "DOCUMENT", doc.id)
    return doc


async def _reindex(session: AsyncSession, doc: Document, content: str | None = None) -> None:
    if content is None:
        version = await current_content(session, doc.id)
        content = version.content if version else None
    await search_service.index_entity(session, doc.id, document_document(doc, content))


# --- Папки -------------------------------------------------------------------


async def list_folders(session: AsyncSession) -> list[DocumentFolder]:
    rows = await session.execute(select(DocumentFolder).order_by(DocumentFolder.path))
    return list(rows.scalars().unique())


async def create_folder(session: AsyncSession, data: dict[str, Any]) -> DocumentFolder:
    parent: DocumentFolder | None = None
    if data.get("parent_id"):
        parent = (
            await session.execute(
                select(DocumentFolder).where(DocumentFolder.id == data["parent_id"])
            )
        ).scalar_one_or_none()
        if parent is None:
            raise NotFound("Родительская папка не найдена")
    folder = DocumentFolder(
        name=data["name"],
        parent_id=parent.id if parent else None,
        description=data.get("description"),
    )
    folder.path = build_path(parent.path if parent else None, folder.name)
    duplicate = (
        await session.execute(select(DocumentFolder.id).where(DocumentFolder.path == folder.path))
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("Папка с таким названием уже есть", path=folder.path)
    session.add(folder)
    await session.flush()
    return folder


async def documents_for_entity(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[Document]:
    rows = await session.execute(
        select(Document)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .where(
            DocumentLink.entity_type == entity_type,
            DocumentLink.entity_id == entity_id,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.title)
    )
    return list(rows.scalars().unique())


async def review_overdue(session: AsyncSession, limit: int = 20) -> list[Document]:
    rows = await session.execute(
        select(Document)
        .where(
            Document.deleted_at.is_(None),
            Document.review_due_on.isnot(None),
            Document.review_due_on <= date.today(),
            or_(Document.status == DocumentStatus.APPROVED,
                Document.status == DocumentStatus.IN_REVIEW),
        )
        .order_by(Document.review_due_on)
        .limit(limit)
    )
    return list(rows.scalars().unique())


PATH_SEP = PATH_SEPARATOR
