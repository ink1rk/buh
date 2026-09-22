from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import replace
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.config import settings
from itms.core.context import ActorKind, Provenance, RequestContext, current_context, set_context
from itms.core.db import session_scope
from itms.core.errors import Forbidden, Unauthorized
from itms.core.security import constant_time_equals
from itms.domain.permissions import Permission, require
from itms.models.directory import UserAccount
from itms.services import auth_service

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _uuid_header(request: Request, name: str) -> uuid.UUID | None:
    raw = request.headers.get(name)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _decode_header_text(raw: str | None) -> str | None:
    """Заголовки передаются в latin-1, поэтому русская причина приходит в percent-encoding."""
    if not raw:
        return None
    value = unquote(raw)
    with suppress(UnicodeEncodeError, UnicodeDecodeError):
        value = value.encode("latin-1").decode("utf-8")
    value = value.strip()[:1000]
    return value or None


def provenance_from_request(request: Request) -> Provenance:
    """Происхождение изменения приходит заголовками и попадает в каждую запись аудита."""
    return Provenance(
        change_id=_uuid_header(request, "X-Change-Id"),
        project_id=_uuid_header(request, "X-Project-Id"),
        task_id=_uuid_header(request, "X-Task-Id"),
        document_id=_uuid_header(request, "X-Document-Id"),
        reason=_decode_header_text(request.headers.get("X-Reason")),
    )


async def current_user(request: Request, session: SessionDep) -> UserAccount:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise Unauthorized("Требуется вход в систему", code_hint="not_authenticated")
    user, user_session = await auth_service.resolve_session(session, token)

    if request.method not in SAFE_METHODS:
        header_token = request.headers.get(settings.csrf_header, "")
        if not header_token or not constant_time_equals(header_token, user_session.csrf_token):
            raise Forbidden("Недействительный CSRF-токен", code_hint="csrf_invalid")

    ctx = current_context()
    set_context(
        replace(
            ctx,
            actor_id=user.id,
            actor_kind=ActorKind.USER,
            actor_label=user.display_name,
            provenance=provenance_from_request(request),
        )
    )
    return user


CurrentUser = Annotated[UserAccount, Depends(current_user)]


def requires(permission: Permission):
    """Объявляет требуемое разрешение у эндпоинта.

    Сейчас полный доступ только у владельца, но проверка единообразна: включение
    ролей исполнителей не потребует переписывания обработчиков.
    """

    async def dependency(user: CurrentUser) -> UserAccount:
        require(user.role, permission)
        return user

    return Depends(dependency)


def base_context(request: Request) -> RequestContext:
    return RequestContext(
        request_id=request.headers.get("X-Request-Id") or str(uuid.uuid4()),
        source="api",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        provenance=provenance_from_request(request),
    )
