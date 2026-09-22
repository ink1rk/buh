from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.documents import (
    DocumentCreate,
    DocumentDetail,
    DocumentLinkRead,
    DocumentLinkWrite,
    DocumentRead,
    DocumentUpdate,
    DocumentVersionRead,
    FolderCreate,
    FolderRead,
)
from itms.domain.permissions import Permission
from itms.models.enums import DocumentStatus
from itms.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


async def _detail(session, doc) -> DocumentDetail:
    version = await document_service.current_content(session, doc.id)
    links = await document_service.links_of(session, doc.id)
    payload = DocumentDetail.model_validate(doc)
    payload.content = version.content if version else ""
    payload.content_format = version.content_format if version else "markdown"
    payload.links = [DocumentLinkRead.model_validate(link) for link in links]
    return payload


@router.get("", response_model=Page[DocumentRead],
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def list_documents(
    session: SessionDep,
    q: str | None = None,
    status: Annotated[list[DocumentStatus] | None, Query()] = None,
    folder_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    review_due: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[DocumentRead]:
    items, total = await document_service.list_documents(
        session,
        q=q,
        status=status,
        folder_id=folder_id,
        entity_type=entity_type,
        entity_id=entity_id,
        review_due=review_due,
        limit=limit,
        offset=offset,
    )
    return Page[DocumentRead](
        items=[DocumentRead.model_validate(doc) for doc in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=DocumentDetail, status_code=201,
             dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def create_document(payload: DocumentCreate, session: SessionDep) -> DocumentDetail:
    data = payload.model_dump(exclude_unset=True)
    data["links"] = [link.model_dump() for link in payload.links]
    doc = await document_service.create_document(session, data)
    return await _detail(session, doc)


@router.get("/folders", response_model=list[FolderRead],
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def list_folders(session: SessionDep) -> list[FolderRead]:
    return [FolderRead.model_validate(f) for f in await document_service.list_folders(session)]


@router.post("/folders", response_model=FolderRead, status_code=201,
             dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def create_folder(payload: FolderCreate, session: SessionDep) -> FolderRead:
    folder = await document_service.create_folder(session, payload.model_dump(exclude_unset=True))
    return FolderRead.model_validate(folder)


@router.get("/{document_id}", response_model=DocumentDetail,
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentDetail:
    doc = await document_service.get_document(session, document_id)
    return await _detail(session, doc)


@router.patch("/{document_id}", response_model=DocumentDetail,
              dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def update_document(
    document_id: uuid.UUID, payload: DocumentUpdate, session: SessionDep
) -> DocumentDetail:
    doc = await document_service.update_document(
        session, document_id, payload.model_dump(exclude_unset=True)
    )
    return await _detail(session, doc)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionRead],
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def list_versions(document_id: uuid.UUID, session: SessionDep) -> list[DocumentVersionRead]:
    versions = await document_service.list_versions(session, document_id)
    return [DocumentVersionRead.model_validate(v) for v in versions]


@router.post("/{document_id}/versions/{version}/restore", response_model=DocumentDetail,
             dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def restore_version(
    document_id: uuid.UUID, version: int, session: SessionDep
) -> DocumentDetail:
    await document_service.restore_version(session, document_id, version)
    doc = await document_service.get_document(session, document_id)
    return await _detail(session, doc)


@router.post("/{document_id}/links", response_model=DocumentLinkRead, status_code=201,
             dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def link_document(
    document_id: uuid.UUID, payload: DocumentLinkWrite, session: SessionDep
) -> DocumentLinkRead:
    link = await document_service.link_document(
        session, document_id, payload.entity_type, payload.entity_id, payload.relation
    )
    return DocumentLinkRead.model_validate(link)


@router.delete("/links/{link_id}", response_model=Ok,
               dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def unlink_document(link_id: uuid.UUID, session: SessionDep) -> Ok:
    await document_service.unlink_document(session, link_id)
    return Ok()


@router.post("/{document_id}/archive", response_model=DocumentRead,
             dependencies=[requires(Permission.DOCUMENT_WRITE)])
async def archive_document(document_id: uuid.UUID, session: SessionDep) -> DocumentRead:
    doc = await document_service.archive_document(session, document_id)
    return DocumentRead.model_validate(doc)
