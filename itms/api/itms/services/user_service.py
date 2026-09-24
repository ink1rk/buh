"""Учётные записи. Отзыв доступа — это блокировка, не удаление."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Forbidden, Invalid, NotFound
from itms.core.security import hash_password, password_problems
from itms.domain.permissions import Permission, has_permission
from itms.models.directory import UserAccount, UserSession
from itms.models.enums import UserRole, UserStatus


async def list_users(session: AsyncSession) -> list[UserAccount]:
    rows = await session.execute(select(UserAccount).order_by(UserAccount.display_name))
    return list(rows.scalars())


async def create_user(
    session: AsyncSession, actor: UserAccount, data: dict[str, Any]
) -> UserAccount:
    role = UserRole(data.get("role") or UserRole.VIEWER)
    _guard_owner_assignment(actor, role)
    email = data["email"]
    exists = (
        await session.execute(
            select(UserAccount.id).where(func.lower(UserAccount.email) == email.lower()).limit(1)
        )
    ).scalar_one_or_none()
    if exists:
        raise Conflict("Учётная запись с таким адресом уже есть", field="email")
    problems = password_problems(data["password"])
    if problems:
        raise Invalid("Пароль не соответствует требованиям", problems=problems)
    user = UserAccount(
        email=email,
        display_name=data["display_name"].strip(),
        password_hash=hash_password(data["password"]),
        role=role,
        status=UserStatus.ACTIVE,
        locale="ru",
        theme="system",
    )
    session.add(user)
    await session.flush()
    return user


async def update_user(
    session: AsyncSession, actor: UserAccount, user_id: uuid.UUID, data: dict[str, Any]
) -> UserAccount:
    user = await session.get(UserAccount, user_id)
    if user is None:
        raise NotFound("Учётная запись не найдена", entity_id=str(user_id))
    if user.role == UserRole.OWNER or data.get("role") == UserRole.OWNER:
        _guard_owner_assignment(actor, UserRole.OWNER)
    next_role = user.role
    if data.get("role") is not None:
        next_role = UserRole(data["role"])
    next_status = user.status
    if data.get("status") is not None:
        next_status = UserStatus(data["status"])
    if next_status == UserStatus.INVITED:
        raise Invalid("Статус приглашения здесь не назначается", code_hint="status_not_assignable")
    if user.id == actor.id and next_status != UserStatus.ACTIVE:
        raise Invalid("Нельзя заблокировать собственный вход", code_hint="self_disable")
    if _loses_owner(user, next_role, next_status):
        others = (
            await session.execute(
                select(func.count())
                .select_from(UserAccount)
                .where(
                    UserAccount.role == UserRole.OWNER,
                    UserAccount.status == UserStatus.ACTIVE,
                    UserAccount.id != user.id,
                )
            )
        ).scalar_one()
        if int(others) == 0:
            raise Conflict(
                "Нельзя снять единственного активного владельца",
                code_hint="last_owner",
            )
    changed = False
    if next_role != user.role:
        user.role = next_role
        changed = True
    if next_status != user.status:
        user.status = next_status
        changed = True
    if changed:
        await session.flush()
        await _revoke_sessions(session, user.id)
    return user


def _guard_owner_assignment(actor: UserAccount, role: UserRole) -> None:
    if role == UserRole.OWNER and not has_permission(actor.role, Permission.USER_GRANT_OWNER):
        raise Forbidden(
            "Назначать владельца может только действующий владелец",
            code_hint="owner_grant_forbidden",
        )


def _loses_owner(user: UserAccount, role: UserRole, status: UserStatus) -> bool:
    return (
        user.role == UserRole.OWNER
        and user.status == UserStatus.ACTIVE
        and (role != UserRole.OWNER or status != UserStatus.ACTIVE)
    )


async def _revoke_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
