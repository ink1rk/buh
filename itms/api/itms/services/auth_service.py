from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.config import settings
from itms.core.context import ActorKind, current_context
from itms.core.errors import Invalid, Unauthorized
from itms.core.security import (
    hash_password,
    needs_rehash,
    new_token,
    password_problems,
    token_fingerprint,
    verify_password,
)
from itms.models.audit import AuditLog
from itms.models.directory import UserAccount, UserSession
from itms.models.enums import AuditAction, UserRole, UserStatus


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: UserAccount
    session_token: str
    csrf_token: str
    expires_at: datetime


async def users_exist(session: AsyncSession) -> bool:
    count = (await session.execute(select(func.count()).select_from(UserAccount))).scalar_one()
    return bool(count)


async def bootstrap_owner(session: AsyncSession) -> tuple[UserAccount, str | None]:
    """Создаёт владельца системы при первой установке.

    Если пароль не задан переменной окружения, он генерируется и возвращается,
    чтобы установщик показал его один раз.
    """
    existing = (
        await session.execute(select(UserAccount).where(UserAccount.role == UserRole.OWNER))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, None

    password = settings.bootstrap_owner_password or secrets.token_urlsafe(12)
    owner = UserAccount(
        email=settings.bootstrap_owner_email.lower(),
        display_name=settings.bootstrap_owner_name,
        password_hash=hash_password(password),
        role=UserRole.OWNER,
        status=UserStatus.ACTIVE,
        locale=settings.default_locale,
    )
    session.add(owner)
    await session.flush()
    return owner, (None if settings.bootstrap_owner_password else password)


async def _write_auth_log(
    session: AsyncSession,
    *,
    action: AuditAction,
    user: UserAccount | None,
    email: str,
    ip: str | None,
) -> None:
    session.add(
        AuditLog(
            actor_id=user.id if user else None,
            actor_kind=ActorKind.USER.value,
            actor_label=user.display_name if user else email,
            request_id=current_context().request_id,
            entity_type="USER",
            entity_id=user.id if user else None,
            entity_label=email,
            action=action,
            source="api",
            ip=ip,
        )
    )


async def authenticate(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> LoginResult:
    user = (
        await session.execute(select(UserAccount).where(UserAccount.email == email.lower().strip()))
    ).scalar_one_or_none()

    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
        await _write_auth_log(
            session, action=AuditAction.LOGIN_FAILED, user=user, email=email, ip=ip
        )
        raise Unauthorized("Неверный адрес электронной почты или пароль",
                           code_hint="invalid_credentials")

    if user.status != UserStatus.ACTIVE:
        await _write_auth_log(
            session, action=AuditAction.LOGIN_FAILED, user=user, email=email, ip=ip
        )
        raise Unauthorized("Учётная запись отключена", code_hint="account_disabled")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    token = new_token()
    csrf = new_token(24)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=token_fingerprint(token),
            csrf_token=csrf,
            expires_at=expires_at,
            ip=ip,
            user_agent=(user_agent or "")[:512] or None,
        )
    )
    user.last_login_at = datetime.now(UTC)
    user.failed_login_count = 0
    await _write_auth_log(session, action=AuditAction.LOGIN, user=user, email=email, ip=ip)
    await session.flush()
    return LoginResult(user=user, session_token=token, csrf_token=csrf, expires_at=expires_at)


async def resolve_session(session: AsyncSession, token: str) -> tuple[UserAccount, UserSession]:
    record = (
        await session.execute(
            select(UserSession).where(UserSession.token_hash == token_fingerprint(token))
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if record is None or record.revoked_at is not None or record.expires_at <= now:
        raise Unauthorized("Сессия недействительна", code_hint="session_invalid")
    idle_limit = timedelta(minutes=settings.session_idle_timeout_minutes)
    if now - record.last_seen_at > idle_limit:
        record.revoked_at = now
        raise Unauthorized("Сессия истекла из-за бездействия", code_hint="session_expired")
    record.last_seen_at = now
    user = record.user
    if user.status != UserStatus.ACTIVE:
        raise Unauthorized("Учётная запись отключена", code_hint="account_disabled")
    return user, record


async def logout(session: AsyncSession, token: str) -> None:
    record = (
        await session.execute(
            select(UserSession).where(UserSession.token_hash == token_fingerprint(token))
        )
    ).scalar_one_or_none()
    if record is None:
        return
    record.revoked_at = datetime.now(UTC)
    await _write_auth_log(
        session,
        action=AuditAction.LOGOUT,
        user=record.user,
        email=record.user.email,
        ip=record.ip,
    )
    await session.flush()


async def change_password(
    session: AsyncSession, user: UserAccount, *, current: str, new: str
) -> None:
    if not user.password_hash or not verify_password(current, user.password_hash):
        raise Unauthorized("Текущий пароль указан неверно", code_hint="invalid_credentials")
    problems = password_problems(new)
    if problems:
        raise Invalid("Пароль не соответствует требованиям", problems=problems)
    user.password_hash = hash_password(new)
    await session.execute(
        UserSession.__table__.update()
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        UserSession.__table__.update()
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def cleanup_sessions(session: AsyncSession) -> int:
    result = await session.execute(
        UserSession.__table__.delete().where(UserSession.expires_at < datetime.now(UTC))
    )
    return int(result.rowcount or 0)
