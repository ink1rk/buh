from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import MfaChallenge, User
from app.core.models import Session as SessionRow
from app.core.security import (
    ROLES,
    AttemptLimiter,
    hash_password,
    new_token,
    token_hash,
    verify_password,
    verify_totp,
)
from app.core.timeutil import utcnow


class AuthError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str,
    mfa_secret: str | None = None,
    mfa_enabled: bool = False,
) -> User:
    if role not in ROLES:
        raise ValueError("unknown role")
    if len(password) < 12:
        raise ValueError("password too short")
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        mfa_secret=mfa_secret,
        mfa_enabled=mfa_enabled,
        is_active=True,
        created_at=utcnow(),
    )
    session.add(user)
    session.flush()
    return user


def issue_session(session: Session, user: User, *, idle_minutes: int = 30, absolute_hours: int = 8) -> dict:
    raw = new_token()
    csrf = new_token()
    now = utcnow()
    row = SessionRow(
        id=token_hash(raw),
        user_id=user.id,
        csrf_token=csrf,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=absolute_hours),
        revoked=False,
    )
    session.add(row)
    add_audit(session, actor=user.username, action="login", entity="session", entity_id=user.id, result="ok")
    session.commit()
    return {"token": raw, "csrf_token": csrf, "role": user.role, "username": user.username, "user_id": user.id}


def login(session: Session, username: str, password: str, limiter: AttemptLimiter) -> dict:
    key = username.strip().lower()
    if limiter.too_many(key):
        add_audit(session, actor=username, action="login", entity="session", result="rate_limited")
        session.commit()
        raise AuthError(429, "too many attempts")
    user = session.query(User).filter_by(username=username).one_or_none()
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        limiter.record(key)
        add_audit(session, actor=username or "anonymous", action="login", entity="session", result="denied")
        session.commit()
        raise AuthError(401, "invalid credentials")
    if user.mfa_enabled:
        raw = new_token()
        session.add(
            MfaChallenge(
                token_hash=token_hash(raw),
                user_id=user.id,
                expires_at=utcnow() + timedelta(minutes=5),
                consumed=False,
            )
        )
        add_audit(session, actor=user.username, action="mfa_challenge", entity="session", entity_id=user.id, result="ok")
        session.commit()
        return {"mfa_required": True, "mfa_token": raw}
    payload = issue_session(session, user)
    payload["mfa_required"] = False
    return payload


def complete_mfa(session: Session, mfa_token: str, code: str, limiter: AttemptLimiter) -> dict:
    row = session.query(MfaChallenge).filter_by(token_hash=token_hash(mfa_token), consumed=False).one_or_none()
    now = utcnow()
    if row is None or row.expires_at < now:
        add_audit(session, actor="anonymous", action="mfa", entity="session", result="denied")
        session.commit()
        raise AuthError(401, "mfa challenge expired")
    user = session.get(User, row.user_id)
    if user is None:
        raise AuthError(401, "mfa challenge expired")
    key = f"mfa:{user.username.lower()}"
    if limiter.too_many(key):
        add_audit(session, actor=user.username, action="mfa", entity="session", result="rate_limited")
        session.commit()
        raise AuthError(429, "too many attempts")
    if not verify_totp(user.mfa_secret or "", code):
        limiter.record(key)
        add_audit(session, actor=user.username, action="mfa", entity="session", entity_id=user.id, result="denied")
        session.commit()
        raise AuthError(401, "invalid mfa code")
    row.consumed = True
    return issue_session(session, user)


def load_session(session: Session, raw_token: str | None, *, idle_minutes: int = 30) -> SessionRow | None:
    if not raw_token:
        return None
    row = session.get(SessionRow, token_hash(raw_token))
    if row is None or row.revoked:
        return None
    now = utcnow()
    if row.expires_at < now:
        add_audit(session, actor=str(row.user_id), action="session", entity="session", entity_id=row.user_id, result="expired")
        session.commit()
        return None
    if now - row.last_seen_at > timedelta(minutes=idle_minutes):
        row.revoked = True
        add_audit(session, actor=str(row.user_id), action="session", entity="session", entity_id=row.user_id, result="idle_expired")
        session.commit()
        return None
    row.last_seen_at = now
    session.commit()
    return row


def change_role(session: Session, actor: User, target_id: int, new_role: str) -> None:
    if actor.role != "OWNER":
        add_audit(session, actor=actor.username, action="change_role", entity="user", entity_id=target_id, result="denied")
        session.commit()
        raise AuthError(403, "forbidden")
    if actor.id == target_id:
        add_audit(session, actor=actor.username, action="change_role", entity="user", entity_id=target_id, result="denied_self")
        session.commit()
        raise AuthError(403, "cannot change own role")
    if new_role not in ROLES:
        raise AuthError(422, "unknown role")
    target = session.get(User, target_id)
    if target is None:
        raise AuthError(404, "user not found")
    before = target.role
    target.role = new_role
    add_audit(
        session,
        actor=actor.username,
        action="change_role",
        entity="user",
        entity_id=target_id,
        result="ok",
        payload={"before": before, "after": new_role},
    )
    session.commit()
