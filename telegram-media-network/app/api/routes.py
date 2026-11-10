from __future__ import annotations

import csv
import io
import json
import socket
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    default_policy,
    get_db,
    get_settings,
    idempotency_lookup,
    idempotency_store,
    require_csrf,
    require_roles,
    require_user,
)
from app.core.config import Settings
from app.core.models import AuditEvent, Channel, Post, PublishingOutbox, Story, User
from app.core.security import AttemptLimiter
from app.core.timeutil import parse_datetime, utcnow
from app.pipeline.types import Fact, SourceItemIn
from app.pipeline.urlsec import SSRFBlocked, assert_url_safe
from app.services.accounts import AuthError, change_role, complete_mfa, create_user, login
from app.services.bootstrap import export_public_config
from app.services.dispatch import publish_preview_or_send, reconcile_outbox
from app.services.editorial import ingest_source_item, story_detail
from app.services.moderation import (
    approve_post,
    policy_from,
    reject_post,
    save_post,
    schedule_post,
    update_runtime,
)

router = APIRouter()


class LoginBody(BaseModel):
    username: str
    password: str


class MfaBody(BaseModel):
    mfa_token: str
    code: str


class RoleBody(BaseModel):
    role: str
    confirm: bool = False


class SettingsBody(BaseModel):
    dry_run: bool | None = None
    publish_enabled: bool | None = None
    global_kill_switch: bool | None = None
    sponsored_enabled: bool | None = None
    confirm: bool = False


class EditBody(BaseModel):
    title: str | None = None
    body: str | None = None
    channel_id: str | None = None


class ReasonBody(BaseModel):
    reason: str = ""
    confirm: bool = False


class ScheduleBody(BaseModel):
    due_utc: datetime
    confirm: bool = False
    override_reason: str = ""


class PublishBody(BaseModel):
    confirm: bool = False


class ReconcileBody(BaseModel):
    decision: str
    message_id: str = ""
    confirm: bool = False


class BulkBody(BaseModel):
    ids: list[int] = Field(default_factory=list)
    reason: str
    confirm: bool = False


class ImportBody(BaseModel):
    url: str
    document: dict | None = None


class CommentBody(BaseModel):
    body: str


class UserBody(BaseModel):
    username: str
    password: str
    role: str


def _guard(exc: AuthError) -> None:
    raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def _limiter(request: Request) -> AttemptLimiter:
    return request.app.state.limiter


@router.get("/health/live")
def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(db: Session = Depends(get_db)) -> dict:
    """Database readiness only. It does not claim that workers or external sites are healthy."""
    db.query(Channel).count()
    return {"status": "ready", "scope": "database"}


@router.get("/health/components")
def health_components(
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    del user
    from app.ops.heartbeat import component_view

    try:
        db.query(Channel).count()
        database = "ok"
    except Exception:
        database = "error"
    collector = component_view(db, "collector")
    scheduler = component_view(db, "scheduler")
    pieces = {
        "database": {"status": database},
        "collector": collector,
        "scheduler": scheduler,
        "media": {"status": "ok" if settings.media_dir.is_dir() else "missing"},
        "redis": {"status": _redis_probe(settings.redis_url)},
    }
    problems = [
        database != "ok",
        collector["status"] != "ok",
        scheduler["status"] != "ok",
        pieces["media"]["status"] == "missing",
        pieces["redis"]["status"] == "unreachable",
    ]
    return {"status": "ok" if not any(problems) else "degraded", "scope": "components", "components": pieces}


def _redis_probe(url: str) -> str:
    if not url:
        return "not_configured"
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port or 6379
    if not host:
        return "unreachable"
    try:
        with socket.create_connection((host, port), 0.3):
            return "reachable"
    except OSError:
        return "unreachable"


@router.post("/api/v1/auth/login")
def auth_login(body: LoginBody, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        payload = login(db, body.username, body.password, _limiter(request))
    except AuthError as exc:
        _guard(exc)
        raise
    response = JSONResponse({key: value for key, value in payload.items() if key != "token"})
    if payload.get("token"):
        response.set_cookie("tmn_session", payload["token"], httponly=True, samesite="lax", path="/")
    return response


@router.post("/api/v1/auth/mfa")
def auth_mfa(body: MfaBody, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        payload = complete_mfa(db, body.mfa_token, body.code, _limiter(request))
    except AuthError as exc:
        _guard(exc)
        raise
    response = JSONResponse({key: value for key, value in payload.items() if key != "token"})
    response.set_cookie("tmn_session", payload["token"], httponly=True, samesite="lax", path="/")
    return response


@router.post("/api/v1/auth/logout")
def auth_logout(auth=Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    _user, row = auth
    row.revoked = True
    db.commit()
    return {"status": "ok"}


@router.get("/api/v1/auth/me")
def auth_me(auth=Depends(require_user)) -> dict:
    user, _row = auth
    return {"username": user.username, "role": user.role, "id": user.id}


@router.get("/api/v1/channels")
def list_channels(auth=Depends(require_user), db: Session = Depends(get_db)) -> list[dict]:
    del auth
    rows = db.query(Channel).order_by(Channel.id).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "publish_enabled": row.publish_enabled,
            "paused": row.paused,
            "daily_cap": row.daily_cap,
            "schedule": row.schedule_json,
            "timezone": row.timezone,
            "require_second_human": row.require_second_human,
        }
        for row in rows
    ]


@router.get("/api/v1/stories")
def list_stories(
    state: str = "",
    channel: str = "",
    auth=Depends(require_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    del auth
    query = db.query(Story)
    if state:
        query = query.filter(Story.status == state)
    if channel:
        query = query.filter(Story.primary_channel_id == channel)
    rows = query.order_by(Story.id.desc()).limit(200).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "score": row.score_total,
            "band": row.score_band,
            "channel_id": row.primary_channel_id,
            "hard_block_reason": row.hard_block_reason,
        }
        for row in rows
    ]


@router.get("/api/v1/stories/{story_id}")
def get_story(story_id: int, auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    payload = story_detail(db, story_id)
    if not payload:
        raise HTTPException(status_code=404, detail="not found")
    return payload


@router.post("/api/v1/stories/import-url")
def import_url(
    body: ImportBody,
    request: Request,
    user: User = Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    del user
    try:
        assert_url_safe(body.url, request.app.state.resolver, request.app.state.allowlist)
    except SSRFBlocked as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    document = body.document
    if document is None:
        fetcher = getattr(request.app.state, "fetch_url", None)
        if fetcher is None:
            raise HTTPException(status_code=409, detail="live fetch is disabled")
        document = fetcher(body.url)
    if not isinstance(document, dict):
        raise HTTPException(status_code=422, detail="document must be a source item")
    item = _item_from_document(document)
    result = ingest_source_item(db, item, media_dir=request.app.state.settings.media_dir)
    return {"status": result.status, "story_id": result.story_id, "blocked_reason": result.blocked_reason}


@router.post("/api/v1/stories/bulk-reject")
def bulk_reject(
    body: BulkBody,
    user: User = Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    changed = 0
    for story_id in body.ids:
        story = db.get(Story, story_id)
        if story is None:
            continue
        story.status = "REJECTED"
        for post in db.query(Post).filter_by(story_id=story.id).all():
            try:
                reject_post(db, post, user, reason=body.reason, confirmed=True)
            except AuthError:
                post.review_status = "REJECTED"
        changed += 1
    db.commit()
    return {"rejected": changed}


@router.patch("/api/v1/posts/{post_id}")
def patch_post(
    post_id: int,
    body: EditBody,
    user: User = Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="not found")
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match required")
    try:
        expected = int(if_match)
    except ValueError as exc:
        raise HTTPException(status_code=428, detail="If-Match required") from exc
    try:
        save_post(db, post, user, title=body.title, body=body.body, channel_id=body.channel_id, expected_version=expected)
    except AuthError as exc:
        _guard(exc)
    return {"id": post.id, "draft_version": post.draft_version, "review_status": post.review_status}


@router.post("/api/v1/posts/{post_id}/approve")
def approve(
    post_id: int,
    body: ReasonBody,
    request: Request,
    user: User = Depends(require_roles("EDITOR", "OWNER", "REVIEWER_SECURITY")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    post = _post(db, post_id)
    payload = body.model_dump()
    slot = idempotency_lookup(db, user, idempotency_key, payload)
    assert slot is not None
    if slot["replay"] is not None:
        return JSONResponse(slot["replay"].response_json, status_code=slot["replay"].status_code)
    try:
        result = approve_post(db, post, user, confirmed=body.confirm)
    except AuthError as exc:
        _guard(exc)
        raise
    idempotency_store(db, user, idempotency_key or "", slot["digest"], 200, result)
    return JSONResponse(result)


@router.post("/api/v1/posts/{post_id}/reject")
def reject(
    post_id: int,
    body: ReasonBody,
    user: User = Depends(require_roles("EDITOR", "OWNER", "REVIEWER_SECURITY")),
    db: Session = Depends(get_db),
) -> dict:
    post = _post(db, post_id)
    try:
        reject_post(db, post, user, reason=body.reason, confirmed=body.confirm)
    except AuthError as exc:
        _guard(exc)
    return {"status": post.review_status}


@router.post("/api/v1/posts/{post_id}/schedule")
def schedule(
    post_id: int,
    body: ScheduleBody,
    user: User = Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    post = _post(db, post_id)
    payload = json.loads(body.model_dump_json())
    slot = idempotency_lookup(db, user, idempotency_key, payload)
    assert slot is not None
    if slot["replay"] is not None:
        return JSONResponse(slot["replay"].response_json, status_code=slot["replay"].status_code)
    try:
        outbox = schedule_post(
            db,
            post,
            user,
            due=body.due_utc,
            confirmed=body.confirm,
            override_reason=body.override_reason,
        )
    except AuthError as exc:
        _guard(exc)
        raise
    result = {"outbox_id": outbox.id, "state": outbox.state, "due_utc": outbox.due_utc.isoformat()}
    idempotency_store(db, user, idempotency_key or "", slot["digest"], 200, result)
    return JSONResponse(result)


@router.post("/api/v1/posts/{post_id}/publish")
def publish(
    post_id: int,
    body: PublishBody,
    request: Request,
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    post = _post(db, post_id)
    slot = idempotency_lookup(db, user, idempotency_key, body.model_dump())
    assert slot is not None
    if slot["replay"] is not None:
        return JSONResponse(slot["replay"].response_json, status_code=slot["replay"].status_code)
    settings: Settings = request.app.state.settings
    policy = policy_from(db, default_policy(settings))
    try:
        result = publish_preview_or_send(
            db,
            post,
            user,
            policy,
            request.app.state.telegram_transport,
            confirmed=body.confirm,
        )
    except AuthError as exc:
        _guard(exc)
        raise
    idempotency_store(db, user, idempotency_key or "", slot["digest"], 200, result)
    return JSONResponse(result)


@router.post("/api/v1/publishing/{outbox_id}/reconcile")
def reconcile(
    outbox_id: int,
    body: ReconcileBody,
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    outbox = db.get(PublishingOutbox, outbox_id)
    if outbox is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        return reconcile_outbox(
            db,
            outbox,
            user,
            decision=body.decision,
            message_id=body.message_id,
            confirmed=body.confirm,
        )
    except AuthError as exc:
        _guard(exc)
        raise


@router.post("/api/v1/channels/{channel_id}/pause")
def pause_channel(
    channel_id: str,
    body: ReasonBody,
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="not found")
    channel.paused = True
    db.commit()
    return {"id": channel.id, "paused": True, "actor": user.username}


@router.post("/api/v1/channels/{channel_id}/resume")
def resume_channel(
    channel_id: str,
    body: ReasonBody,
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="not found")
    channel.paused = False
    db.commit()
    return {"id": channel.id, "paused": False, "actor": user.username}


@router.post("/api/v1/system/settings")
def system_settings(
    body: SettingsBody,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    _user, _row = (user if isinstance(user, tuple) else (user, None))
    actor = user[0] if isinstance(user, tuple) else user
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    changes = {
        key: value
        for key, value in body.model_dump().items()
        if key != "confirm" and value is not None
    }
    try:
        return update_runtime(db, actor, changes)
    except AuthError as exc:
        _guard(exc)
        raise


@router.post("/api/v1/users")
def create_account(
    body: UserBody,
    user: User = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    del user
    try:
        created = create_user(db, username=body.username, password=body.password, role=body.role)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": created.id, "role": created.role}


@router.post("/api/v1/users/{user_id}/role")
def set_role(
    user_id: int,
    body: RoleBody,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    actor = user[0] if isinstance(user, tuple) else user
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    try:
        change_role(db, actor, user_id, body.role)
    except AuthError as exc:
        _guard(exc)
    target = db.get(User, user_id)
    return {"id": user_id, "role": target.role if target else None}


@router.get("/api/v1/metrics")
def metrics(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return {"channels": [_channel_metrics(db, row) for row in db.query(Channel).all()]}


@router.get("/metrics")
def prometheus(auth=Depends(require_user)) -> Response:
    del auth
    from app.ops.metrics import COUNTERS

    return Response(COUNTERS.render(), media_type="text/plain; version=0.0.4")


@router.get("/api/v1/export/config.json")
def export_config(auth=Depends(require_user), settings: Settings = Depends(get_settings)) -> dict:
    del auth
    return export_public_config(settings.config_dir)


@router.get("/api/v1/export/audit.json")
def export_audit_json(auth=Depends(require_user), db: Session = Depends(get_db)) -> list[dict]:
    del auth
    return [_audit_dict(row) for row in db.query(AuditEvent).order_by(AuditEvent.id).limit(1000)]


@router.get("/api/v1/export/audit.csv")
def export_audit_csv(auth=Depends(require_user), db: Session = Depends(get_db)) -> Response:
    del auth
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["id", "actor", "action", "entity", "entity_id", "result", "created_at"])
    writer.writeheader()
    for row in db.query(AuditEvent).order_by(AuditEvent.id).limit(1000):
        payload = _audit_dict(row)
        payload.pop("payload_redacted", None)
        writer.writerow(payload)
    return Response(buffer.getvalue(), media_type="text/csv")


@router.get("/api/v1/analytics")
def analytics(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return {
        "views_available": False,
        "note": "Просмотры постов Telegram через Bot API недоступны. Значение не подставляется.",
        "channels": [_channel_metrics(db, row) for row in db.query(Channel).all()],
    }


@router.post("/api/v1/posts/{post_id}/comments")
def comment(
    post_id: int,
    body: CommentBody,
    user: User = Depends(require_roles("EDITOR", "OWNER", "REVIEWER_SECURITY", "VIEWER")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.moderation import add_comment

    post = _post(db, post_id)
    try:
        row = add_comment(db, post, user, body.body)
    except AuthError as exc:
        _guard(exc)
        raise
    return {"id": row.id}


def _post(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="not found")
    return post


def _audit_dict(row: AuditEvent) -> dict:
    return {
        "id": row.id,
        "actor": row.actor,
        "action": row.action,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "result": row.result,
        "created_at": row.created_at.isoformat(),
        "payload_redacted": row.payload_redacted,
    }


def _channel_metrics(db: Session, channel: Channel) -> dict:
    from app.core.models import AnalyticsDaily

    manual = (
        db.query(AnalyticsDaily)
        .filter_by(channel_id=channel.id)
        .order_by(AnalyticsDaily.metric_date.desc())
        .first()
    )
    if manual is not None and manual.views_source == "manual" and manual.views_manual is not None:
        views = manual.views_manual
        label = str(manual.views_manual)
        source = "manual"
    else:
        views = None
        label = "н/д"
        source = None
    return {
        "channel_id": channel.id,
        "views": views,
        "views_label": label,
        "measurement_source": source,
        "subscribers": None,
    }


def _item_from_document(data: dict) -> SourceItemIn:
    facts = [
        Fact(
            id=fact["id"],
            statement=fact["statement"],
            evidence_url=fact["evidence_url"],
            evidence_excerpt=fact["evidence_excerpt"],
        )
        for fact in data.get("facts", [])
    ]
    return SourceItemIn(
        source_id=data["source_id"],
        source_external_id=data["source_external_id"],
        source_url=data["source_url"],
        title=data["title"],
        discovered_at=parse_datetime(data.get("discovered_at")) or utcnow(),
        published_at=parse_datetime(data.get("published_at")),
        raw_sha256=data["raw_sha256"],
        license_state=data["license_state"],
        facts=facts,
        canonical_url=data.get("canonical_url"),
        content_kind=data.get("content_kind") or "news",
        license_spdx=data.get("license_spdx"),
        is_preprint=bool(data.get("is_preprint")),
    )
