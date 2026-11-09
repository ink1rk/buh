from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.config import Settings
from app.core.models import IdempotencyRecord, User
from app.core.security import Policy
from app.services.accounts import load_session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def optional_user(request: Request, db: Session = Depends(get_db)) -> tuple[User, object] | None:
    raw = request.cookies.get("tmn_session")
    settings: Settings = request.app.state.settings
    row = load_session(db, raw, idle_minutes=settings.session_idle_minutes)
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user, row


def require_user(request: Request, db: Session = Depends(get_db)) -> tuple[User, object]:
    found = optional_user(request, db)
    if found is None:
        if request.method != "GET":
            add_audit(db, actor="anonymous", action=request.url.path, entity="auth", result="denied")
            db.commit()
        raise HTTPException(status_code=401, detail="authentication required")
    return found


def require_csrf(request: Request, auth=Depends(require_user)) -> tuple[User, object]:
    user, row = auth
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        header = request.headers.get("x-csrf-token", "")
        if not header or header != row.csrf_token:
            raise HTTPException(status_code=403, detail="csrf failed")
    return user, row


def require_roles(*roles: str):
    def checker(auth=Depends(require_csrf)) -> User:
        user, _row = auth
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return checker


def default_policy(settings: Settings) -> Policy:
    return Policy(
        dry_run=settings.dry_run,
        publish_enabled=settings.publish_enabled,
        kill_switch=settings.global_kill_switch,
        sponsored_enabled=settings.sponsored_enabled,
    )


def idempotency_lookup(db: Session, user: User, key: str | None, payload: dict) -> dict | None:
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key required")
    digest = __import__("hashlib").sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    existing = db.query(IdempotencyRecord).filter_by(key=key, user_id=user.id).one_or_none()
    if existing is None:
        return {"digest": digest, "replay": None}
    if existing.request_hash != digest:
        raise HTTPException(status_code=409, detail="idempotency key reused with a different body")
    return {"digest": digest, "replay": existing}


def idempotency_store(db: Session, user: User, key: str, digest: str, status_code: int, body: dict) -> None:
    db.add(
        IdempotencyRecord(
            key=key,
            user_id=user.id,
            request_hash=digest,
            response_json=body,
            status_code=status_code,
        )
    )
    db.commit()
