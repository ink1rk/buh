from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.config import settings
from itms.core.context import current_context
from itms.core.errors import Invalid, NotFound
from itms.infra.storage import build_key, content_hash, get_storage
from itms.models.documents import Attachment, FileObject

#: Исполняемые типы не принимаем: файлы отдаются по подписанной ссылке,
#: но лишний риск в системе документации не нужен.
BLOCKED_EXTENSIONS = frozenset(
    {".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".js", ".vbs", ".ps1", ".sh", ".jar"}
)
_SAFE_NAME_RE = re.compile(r"[^\w\s.()\[\]«»„“”+=@-]", re.UNICODE)


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].strip()
    name = _SAFE_NAME_RE.sub("_", name)
    return name[:255] or "file"


def validate_upload(filename: str, size: int) -> None:
    if size <= 0:
        raise Invalid("Пустой файл", code_hint="empty_file")
    if size > settings.upload_max_bytes:
        raise Invalid(
            "Файл превышает допустимый размер",
            code_hint="file_too_large",
            max_bytes=settings.upload_max_bytes,
        )
    lowered = filename.lower()
    if any(lowered.endswith(ext) for ext in BLOCKED_EXTENSIONS):
        raise Invalid("Такой тип файла загружать нельзя", code_hint="file_type_blocked")


async def store_file(
    session: AsyncSession,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    prefix: str = "files",
) -> FileObject:
    safe_name = sanitize_filename(filename)
    validate_upload(safe_name, len(content))
    digest = content_hash(content)

    existing = (
        await session.execute(select(FileObject).where(FileObject.sha256 == digest).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    key = build_key(prefix, digest, safe_name)
    get_storage().put(key, content, content_type or "application/octet-stream")
    file_object = FileObject(
        storage_key=key,
        filename=safe_name,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(content),
        sha256=digest,
        uploaded_by=current_context().actor_id,
    )
    session.add(file_object)
    await session.flush()
    return file_object


async def get_file(session: AsyncSession, file_id: uuid.UUID) -> FileObject:
    file_object = (
        await session.execute(select(FileObject).where(FileObject.id == file_id))
    ).scalar_one_or_none()
    if file_object is None:
        raise NotFound("Файл не найден", entity_id=str(file_id))
    return file_object


async def read_file(session: AsyncSession, file_id: uuid.UUID) -> tuple[FileObject, bytes]:
    file_object = await get_file(session, file_id)
    return file_object, get_storage().get(file_object.storage_key)


def content_disposition(filename: str) -> str:
    """Имя файла может быть на русском, а заголовок ограничен latin-1 (RFC 5987)."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def download_url(file_object: FileObject) -> str | None:
    return get_storage().presigned_url(file_object.storage_key, file_object.filename)


async def attach(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    title: str | None = None,
) -> Attachment:
    await get_file(session, file_id)
    attachment = Attachment(
        file_id=file_id,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        created_by=current_context().actor_id,
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def list_attachments(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Attachment)
            .where(Attachment.entity_type == entity_type, Attachment.entity_id == entity_id)
            .order_by(Attachment.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": a.id,
            "file_id": a.file_id,
            "filename": a.file.filename,
            "content_type": a.file.content_type,
            "size_bytes": a.file.size_bytes,
            "title": a.title,
            "created_at": a.created_at,
        }
        for a in rows
    ]
