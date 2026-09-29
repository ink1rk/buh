from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from itms.api.deps import SessionDep, requires
from itms.api.schemas.documents import AttachmentRead, FileRead
from itms.domain.permissions import Permission
from itms.services import file_service

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileRead, status_code=201,
             dependencies=[requires(Permission.FILE_UPLOAD)])
async def upload_file(
    session: SessionDep,
    file: UploadFile = File(...),
    entity_type: str | None = Form(default=None),
    entity_id: uuid.UUID | None = Form(default=None),
    title: str | None = Form(default=None),
) -> FileRead:
    content = await file.read()
    stored = await file_service.store_file(
        session,
        filename=file.filename or "file",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    if entity_type and entity_id:
        await file_service.attach(
            session,
            file_id=stored.id,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
        )
    payload = FileRead.model_validate(stored)
    payload.download_url = file_service.download_url(stored)
    return payload


@router.get("/{file_id}", response_model=FileRead,
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def get_file(file_id: uuid.UUID, session: SessionDep) -> FileRead:
    stored = await file_service.get_file(session, file_id)
    payload = FileRead.model_validate(stored)
    payload.download_url = file_service.download_url(stored)
    return payload


@router.get("/{file_id}/content", dependencies=[requires(Permission.DOCUMENT_READ)])
async def download_file(file_id: uuid.UUID, session: SessionDep) -> Response:
    stored, content = await file_service.read_file(session, file_id)
    return Response(
        content=content,
        media_type=stored.content_type,
        headers={"Content-Disposition": file_service.content_disposition(stored.filename)},
    )


@router.get("/attachments/{entity_type}/{entity_id}", response_model=list[AttachmentRead],
            dependencies=[requires(Permission.DOCUMENT_READ)])
async def list_attachments(
    entity_type: str, entity_id: uuid.UUID, session: SessionDep
) -> list[AttachmentRead]:
    rows = await file_service.list_attachments(session, entity_type, entity_id)
    return [AttachmentRead.model_validate(row) for row in rows]
