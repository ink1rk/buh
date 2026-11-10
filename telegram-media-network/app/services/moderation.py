from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import (
    AdCampaign,
    ApprovalEvent,
    Channel,
    Comment,
    MediaAsset,
    Post,
    PostVersion,
    PublishingOutbox,
    Story,
    User,
)
from app.core.security import Policy
from app.core.timeutil import ensure_utc, utcnow
from app.pipeline.caption import build_caption, caption_hash, validate_caption
from app.pipeline.editor import license_claim_blocked
from app.publishing.photo import card_gap
from app.publishing.schedule import gap_ok, quiet
from app.services.accounts import AuthError

ACTIVE_OUTBOX = ("scheduled", "sending", "retryable_failed", "paused", "needs_reconciliation")


def _cancel_active(session: Session, post_id: int) -> None:
    rows = (
        session.query(PublishingOutbox)
        .filter(PublishingOutbox.post_id == post_id, PublishingOutbox.state.in_(ACTIVE_OUTBOX))
        .all()
    )
    for row in rows:
        row.state = "cancelled"


def _sponsored_blocked(session: Session, post: Post) -> str:
    flags = post.flags_json or []
    if "sponsored" not in flags and post.sponsored_campaign_id is None:
        return ""
    if post.sponsored_campaign_id is None:
        return "sponsor_without_campaign"
    campaign = session.get(AdCampaign, post.sponsored_campaign_id)
    if campaign is None or campaign.legal_status != "approved" or not campaign.marked:
        return "sponsor_legal_pending"
    return ""


def _invalidate_cards(session: Session, post: Post) -> None:
    rows = session.query(MediaAsset).filter_by(post_id=post.id, kind="card", status="ready").all()
    for row in rows:
        row.status = "stale"


def _discard_partial(directory: Path, post: Post) -> None:
    partial = directory / f".post-{post.id}-v{post.draft_version}.jpg.partial"
    partial.unlink(missing_ok=True)


def save_post(
    session: Session,
    post: Post,
    actor: User,
    *,
    title: str | None,
    body: str | None,
    channel_id: str | None,
    expected_version: int,
    media_dir: Path | None = None,
) -> Post:
    if actor.role not in {"EDITOR", "OWNER"}:
        raise AuthError(403, "forbidden")
    if post.draft_version != expected_version:
        raise AuthError(409, "version conflict")
    changed = False
    if title is not None and title != post.title:
        post.title = title[:100]
        changed = True
    if body is not None and body != post.body:
        post.body = body[:900]
        changed = True
    if channel_id is not None and channel_id != post.channel_id:
        post.channel_id = channel_id
        changed = True
    if changed:
        post.draft_version += 1
        post.publish_intent_id = secrets.token_hex(8)
        post.approver_ids_json = []
        if post.review_status != "REJECTED":
            post.review_status = "NEEDS_REVIEW"
        post.final_hash = hashlib.sha256(
            f"{post.channel_id}|{post.draft_version}|{post.title}|{post.body}".encode()
        ).hexdigest()
        post.caption = build_caption(post.title, post.body, post.source_links_json or [], post.hashtags_json or [])
        post.caption_hash = caption_hash(post.caption)
        _cancel_active(session, post.id)
        _invalidate_cards(session, post)
        if media_dir is not None:
            channel = session.get(Channel, post.channel_id)
            if channel is not None:
                from app.services.editorial import refresh_card

                try:
                    session.add(refresh_card(post, channel, media_dir))
                except Exception:
                    _discard_partial(media_dir, post)
        session.add(
            PostVersion(
                post_id=post.id,
                version=post.draft_version,
                title=post.title,
                body=post.body,
                channel_id=post.channel_id,
                final_hash=post.final_hash,
                editor_id=actor.id,
                created_at=utcnow(),
            )
        )
    add_audit(session, actor=actor.username, action="edit_post", entity="post", entity_id=post.id, result="ok")
    session.commit()
    return post


def approve_post(session: Session, post: Post, actor: User, *, confirmed: bool) -> dict:
    if not confirmed:
        raise AuthError(400, "confirmation required")
    if actor.role not in {"EDITOR", "OWNER", "REVIEWER_SECURITY"}:
        add_audit(session, actor=actor.username, action="approve", entity="post", entity_id=post.id, result="denied")
        session.commit()
        raise AuthError(403, "forbidden")
    story = session.get(Story, post.story_id)
    if story and story.hard_block_reason:
        raise AuthError(409, story.hard_block_reason)
    if license_claim_blocked(f"{post.title}\n{post.body}", story.license_state if story else "unknown"):
        raise AuthError(422, "unsupported license claim")
    if card_gap(session, post):
        raise AuthError(409, "stale_card")
    sponsor = _sponsored_blocked(session, post)
    if sponsor:
        add_audit(session, actor=actor.username, action="approve", entity="post", entity_id=post.id, result="denied", payload={"reason": sponsor})
        session.commit()
        raise AuthError(403, sponsor)
    ok, problem = validate_caption(post.caption or "", post.body)
    if not ok:
        raise AuthError(422, problem)
    approvers = list(post.approver_ids_json or [])
    if actor.id in approvers:
        raise AuthError(409, "this reviewer already approved")
    required = post.approvals_required or 1
    if required >= 2 and approvers and actor.role not in {"REVIEWER_SECURITY", "OWNER"}:
        add_audit(session, actor=actor.username, action="approve", entity="post", entity_id=post.id, result="denied")
        session.commit()
        raise AuthError(403, "second reviewer must be security or owner")
    if actor.role == "REVIEWER_SECURITY" and required < 2 and not approvers:
        raise AuthError(403, "security reviewer confirms the second step")
    before = post.final_hash
    approvers.append(actor.id)
    post.approver_ids_json = approvers
    complete = len(approvers) >= required
    post.review_status = "APPROVED" if complete else "NEEDS_REVIEW"
    session.add(
        ApprovalEvent(
            post_id=post.id,
            actor_id=actor.id,
            action="approve" if complete else "first_approval",
            reason="",
            before_hash=before,
            after_hash=post.final_hash,
            created_at=utcnow(),
        )
    )
    add_audit(
        session,
        actor=actor.username,
        action="approve",
        entity="post",
        entity_id=post.id,
        result="approved" if complete else "needs_second",
    )
    session.commit()
    return {"status": post.review_status, "approvals": len(approvers), "required": required}


def reject_post(session: Session, post: Post, actor: User, *, reason: str, confirmed: bool) -> None:
    if not confirmed:
        raise AuthError(400, "confirmation required")
    if actor.role not in {"EDITOR", "OWNER", "REVIEWER_SECURITY"}:
        raise AuthError(403, "forbidden")
    if not reason.strip():
        raise AuthError(422, "reason required")
    post.review_status = "REJECTED"
    story = session.get(Story, post.story_id)
    if story is not None:
        story.status = "REJECTED"
    _cancel_active(session, post.id)
    session.add(
        ApprovalEvent(
            post_id=post.id,
            actor_id=actor.id,
            action="reject",
            reason=reason[:500],
            before_hash=post.final_hash,
            after_hash=post.final_hash,
            created_at=utcnow(),
        )
    )
    add_audit(session, actor=actor.username, action="reject", entity="post", entity_id=post.id, result="ok")
    session.commit()


def add_comment(session: Session, post: Post, actor: User, body: str) -> Comment:
    if actor.role == "SERVICE":
        raise AuthError(403, "forbidden")
    comment = Comment(post_id=post.id, actor_id=actor.id, body=body[:2000], created_at=utcnow())
    session.add(comment)
    session.commit()
    return comment


def schedule_post(
    session: Session,
    post: Post,
    actor: User,
    *,
    due: datetime,
    confirmed: bool,
    override_reason: str = "",
    now: datetime | None = None,
) -> PublishingOutbox:
    if not confirmed:
        raise AuthError(400, "confirmation required")
    if actor.role not in {"EDITOR", "OWNER"}:
        raise AuthError(403, "forbidden")
    if post.review_status != "APPROVED":
        raise AuthError(409, "post is not approved")
    if card_gap(session, post):
        raise AuthError(409, "stale_card")
    sponsor = _sponsored_blocked(session, post)
    if sponsor:
        raise AuthError(403, sponsor)
    ok, problem = validate_caption(post.caption or "", post.body)
    if not ok:
        raise AuthError(422, problem)
    channel = session.get(Channel, post.channel_id)
    if channel is None:
        raise AuthError(404, "channel missing")
    moment = ensure_utc(due)
    current = ensure_utc(now or utcnow())
    if quiet(moment, channel.quiet_start, channel.quiet_end) and not (actor.role == "OWNER" and override_reason):
        raise AuthError(409, "quiet hours")
    existing = [
        row.due_utc
        for row in session.query(PublishingOutbox).filter(
            PublishingOutbox.channel_id == channel.id,
            PublishingOutbox.state.in_(("scheduled", "sending", "published")),
        )
    ]
    if not gap_ok(existing, moment, channel.min_gap_minutes):
        raise AuthError(409, "min gap")
    story = session.get(Story, post.story_id)
    if story is not None:
        _enforce_cooldown(session, story, post, actor, override_reason, current)
    active = (
        session.query(PublishingOutbox)
        .filter(PublishingOutbox.post_id == post.id, PublishingOutbox.state.in_(ACTIVE_OUTBOX))
        .one_or_none()
    )
    if active is not None:
        return active
    key = hashlib.sha256(
        f"{post.channel_id}|{post.id}|{post.draft_version}|{post.publish_intent_id}".encode()
    ).hexdigest()
    outbox = PublishingOutbox(
        post_id=post.id,
        channel_id=post.channel_id,
        due_utc=moment,
        idempotency_key=key,
        state="scheduled",
        publish_intent_id=post.publish_intent_id,
        caption_hash=post.caption_hash,
        attempts=0,
        request_sent=False,
    )
    session.add(outbox)
    post.review_status = "SCHEDULED"
    add_audit(session, actor=actor.username, action="schedule", entity="post", entity_id=post.id, result="ok")
    session.commit()
    return outbox


def _enforce_cooldown(session: Session, story: Story, post: Post, actor: User, override_reason: str, now: datetime) -> None:
    window = now - timedelta(hours=48)
    from app.core.models import PublishedMessage

    recent = (
        session.query(PublishedMessage)
        .join(Post, Post.id == PublishedMessage.post_id)
        .join(Story, Story.id == Post.story_id)
        .filter(Story.cluster_id == story.cluster_id, PublishedMessage.published_utc >= window)
        .first()
    )
    if recent is not None:
        if not (actor.role == "OWNER" and override_reason.strip()):
            raise AuthError(409, "cluster cooldown")
        add_audit(
            session,
            actor=actor.username,
            action="cooldown_override",
            entity="story",
            entity_id=story.id,
            result="ok",
            payload={"reason": override_reason[:300]},
        )
    if story.repo_identity:
        repo_window = now - timedelta(days=30)
        repo_recent = (
            session.query(PublishedMessage)
            .join(Post, Post.id == PublishedMessage.post_id)
            .join(Story, Story.id == Post.story_id)
            .filter(Story.repo_identity == story.repo_identity, PublishedMessage.published_utc >= repo_window)
            .first()
        )
        if repo_recent is not None and story.content_kind != "release":
            if not (actor.role == "OWNER" and override_reason.strip()):
                raise AuthError(409, "repo cooldown")


def policy_from(session: Session, defaults: Policy) -> Policy:
    from app.core.models import RuntimeSetting

    def flag(key: str, default: bool) -> bool:
        row = session.get(RuntimeSetting, key)
        if row is None:
            return default
        return bool((row.value_json or {}).get("value"))

    return Policy(
        dry_run=flag("dry_run", defaults.dry_run),
        publish_enabled=flag("publish_enabled", defaults.publish_enabled),
        kill_switch=flag("global_kill_switch", defaults.kill_switch),
        sponsored_enabled=flag("sponsored_enabled", defaults.sponsored_enabled),
    )


def update_runtime(session: Session, actor: User, changes: dict) -> dict:
    from app.core.models import RuntimeSetting

    if actor.role != "OWNER":
        add_audit(session, actor=actor.username, action="system_settings", entity="runtime", result="denied")
        session.commit()
        raise AuthError(403, "forbidden")
    allowed = {"dry_run", "publish_enabled", "global_kill_switch", "sponsored_enabled"}
    applied = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        row = session.get(RuntimeSetting, key)
        if row is None:
            row = RuntimeSetting(key=key)
            session.add(row)
        row.value_json = {"value": bool(value)}
        row.updated_at = utcnow()
        row.updated_by = actor.username
        applied[key] = bool(value)
    add_audit(session, actor=actor.username, action="system_settings", entity="runtime", result="ok", payload=applied)
    session.commit()
    return applied
