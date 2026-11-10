from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.config import ROOT
from app.core.models import Alert, Channel, Post, PublishedMessage, PublishingOutbox, Story, User
from app.core.security import Policy
from app.core.timeutil import ensure_utc, msk_day_bounds, utcnow
from app.ops.metrics import COUNTERS
from app.publishing.photo import CardError, load_card
from app.publishing.schedule import DueItem, select_sendable, slot_due
from app.publishing.telegram import AmbiguousTimeout, DeliveryRejected
from app.services.accounts import AuthError
from app.services.moderation import ACTIVE_OUTBOX, _sponsored_blocked

FRESH_HOURS = 36


class CrashBeforeCommit(Exception):
    pass


@dataclass
class TickResult:
    leader: bool
    scheduled: int = 0
    sent: int = 0
    blocked: str = ""


def raise_alert(
    session: Session,
    code: str,
    message: str,
    *,
    channel_id: str = "",
    now: datetime | None = None,
    cooldown_minutes: int = 30,
) -> Alert:
    moment = ensure_utc(now or utcnow())
    recent = (
        session.query(Alert)
        .filter(
            Alert.code == code,
            Alert.channel_id == channel_id,
            Alert.created_at >= moment - timedelta(minutes=cooldown_minutes),
        )
        .first()
    )
    if recent is not None:
        return recent
    alert = Alert(severity="warning", code=code, message=message[:500], channel_id=channel_id, created_at=moment)
    session.add(alert)
    return alert


def claim_outbox(session: Session, outbox_id: int) -> int | None:
    row = session.execute(
        select(PublishingOutbox)
        .where(PublishingOutbox.id == outbox_id, PublishingOutbox.state == "scheduled")
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if row is None:
        return None
    row.state = "sending"
    row.lease_until = utcnow() + timedelta(seconds=60)
    session.flush()
    return row.id


def recover_inflight(session: Session, now: datetime | None = None) -> int:
    moment = ensure_utc(now or utcnow())
    rows = (
        session.query(PublishingOutbox)
        .filter(PublishingOutbox.state == "sending", PublishingOutbox.lease_until.is_not(None), PublishingOutbox.lease_until < moment)
        .all()
    )
    for row in rows:
        row.state = "needs_reconciliation"
        row.last_error = "lease_expired_without_ack"
        post = session.get(Post, row.post_id)
        if post is not None and post.review_status == "SENDING":
            post.review_status = "NEEDS_RECONCILIATION"
        COUNTERS.inc("publish_ambiguous_total")
    session.commit()
    return len(rows)


def dispatch_outbox(
    session: Session,
    outbox: PublishingOutbox,
    transport,
    *,
    now: datetime | None = None,
    crash_before_commit: bool = False,
    media_dir: Path | None = None,
    allowed_chat_id: str = "",
) -> dict:
    moment = ensure_utc(now or utcnow())
    if outbox.state not in {"scheduled", "retryable_failed"}:
        return {"state": outbox.state, "calls": 0}
    if outbox.state == "retryable_failed" and outbox.due_utc and ensure_utc(outbox.due_utc) > moment:
        return {"state": outbox.state, "calls": 0, "waiting": True}
    channel = session.get(Channel, outbox.channel_id)
    post = session.get(Post, outbox.post_id)
    if channel is None or post is None:
        return {"state": "missing"}
    directory = media_dir or (ROOT / "var" / "media")
    try:
        photo, digest = load_card(session, post, directory)
    except CardError as exc:
        outbox.attempts += 1
        outbox.state = "dlq" if outbox.attempts >= 4 else "retryable_failed"
        outbox.due_utc = moment + timedelta(minutes=30)
        outbox.last_error = exc.reason
        post.review_status = "SCHEDULED"
        session.commit()
        return {"state": outbox.state, "reason": exc.reason, "calls": 0}
    allowed = str(allowed_chat_id or "")
    if allowed and str(channel.chat_id or "") != allowed:
        outbox.state = "dlq"
        outbox.last_error = "foreign_chat"
        post.review_status = "SCHEDULED"
        add_audit(session, actor="publisher", action="publish", entity="outbox", entity_id=outbox.id, result="foreign_chat")
        session.commit()
        return {"state": "dlq", "reason": "foreign_chat", "calls": 0}
    outbox.state = "sending"
    outbox.lease_until = moment + timedelta(seconds=60)
    outbox.request_sent = False
    post.review_status = "SENDING"
    session.commit()
    payload = {
        "chat_id": channel.chat_id or "unset",
        "caption": post.caption,
        "caption_hash": post.caption_hash,
        "photo": photo,
        "photo_sha256": digest,
    }
    try:
        result = transport.send_photo(payload)
    except AmbiguousTimeout:
        outbox.state = "needs_reconciliation"
        outbox.request_sent = True
        outbox.last_error = "ambiguous_timeout"
        post.review_status = "NEEDS_RECONCILIATION"
        raise_alert(session, "ambiguous_publish", "Исход отправки не подтверждён. Нужна ручная сверка.", channel_id=channel.id, now=moment)
        COUNTERS.inc("publish_ambiguous_total")
        add_audit(session, actor="publisher", action="publish", entity="outbox", entity_id=outbox.id, result="needs_reconciliation")
        session.commit()
        return {"state": "needs_reconciliation"}
    except DeliveryRejected as exc:
        outbox.attempts += 1
        outbox.state = "dlq" if outbox.attempts >= 4 else "retryable_failed"
        outbox.due_utc = moment + timedelta(seconds=min(300, 2 ** max(1, outbox.attempts)))
        outbox.last_error = str(exc)[:200]
        post.review_status = "SCHEDULED"
        session.commit()
        return {"state": outbox.state}
    if result.status in {401, 403}:
        channel.paused = True
        outbox.state = "paused"
        outbox.last_error = f"telegram_{result.status}"
        post.review_status = "PAUSED"
        raise_alert(session, f"telegram_{result.status}", "Канал поставлен на паузу: Bot API отказал в доступе.", channel_id=channel.id, now=moment)
        COUNTERS.inc("publish_attempt_total_denied")
        add_audit(session, actor="publisher", action="publish", entity="channel", entity_id=channel.id, result="paused")
        session.commit()
        return {"state": "paused", "status": result.status}
    if result.status == 429:
        delay = 1 if result.retry_after is None else int(result.retry_after)
        if delay < 1:
            delay = 1
        outbox.attempts += 1
        outbox.state = "dlq" if outbox.attempts >= 4 else "retryable_failed"
        outbox.due_utc = moment + timedelta(seconds=delay)
        outbox.next_attempt_at = outbox.due_utc
        outbox.last_error = "rate_limited"
        post.review_status = "SCHEDULED"
        COUNTERS.inc("telegram_429_total")
        session.commit()
        return {"state": outbox.state, "delay": delay}
    if result.status == 200 and result.message_id:
        outbox.request_sent = True
        outbox.pending_message_id = str(result.message_id)
        session.commit()
        message = PublishedMessage(
            post_id=post.id,
            channel_id=channel.id,
            telegram_message_id=str(result.message_id),
            published_utc=moment,
            telegram_link="",
            caption_hash=post.caption_hash,
        )
        session.add(message)
        outbox.state = "published"
        post.review_status = "PUBLISHED"
        if crash_before_commit:
            session.rollback()
            COUNTERS.inc("publish_attempt_total_crashed")
            return {"state": "sending", "crashed": True}
        COUNTERS.inc("publish_attempt_total_ok")
        add_audit(
            session,
            actor="publisher",
            action="publish",
            entity="post",
            entity_id=post.id,
            result="published",
            payload={"message_id": str(result.message_id), "caption_hash": post.caption_hash},
        )
        session.commit()
        return {"state": "published", "message_id": str(result.message_id), "caption_hash": post.caption_hash}
    outbox.state = "retryable_failed"
    outbox.last_error = f"status_{result.status}"
    post.review_status = "SCHEDULED"
    session.commit()
    return {"state": outbox.state, "status": result.status}


def reconcile_outbox(
    session: Session,
    outbox: PublishingOutbox,
    actor: User,
    *,
    decision: str,
    message_id: str = "",
    confirmed: bool = False,
) -> dict:
    if actor.role != "OWNER":
        raise AuthError(403, "forbidden")
    if not confirmed:
        raise AuthError(400, "confirmation required")
    if outbox.state != "needs_reconciliation":
        raise AuthError(409, "outbox is not awaiting reconciliation")
    post = session.get(Post, outbox.post_id)
    if decision == "found":
        if not message_id:
            raise AuthError(422, "message id required")
        session.add(
            PublishedMessage(
                post_id=outbox.post_id,
                channel_id=outbox.channel_id,
                telegram_message_id=message_id,
                published_utc=utcnow(),
                telegram_link="",
                caption_hash=outbox.caption_hash,
            )
        )
        outbox.state = "published"
        if post is not None:
            post.review_status = "PUBLISHED"
        result = "found"
    elif decision == "absent":
        outbox.state = "scheduled"
        outbox.request_sent = False
        outbox.due_utc = utcnow() + timedelta(hours=1)
        outbox.lease_until = None
        if post is not None:
            post.review_status = "SCHEDULED"
        result = "absent"
    else:
        raise AuthError(422, "decision must be found or absent")
    add_audit(session, actor=actor.username, action="reconcile", entity="outbox", entity_id=outbox.id, result=result)
    session.commit()
    return {"state": outbox.state}


def publish_preview_or_send(
    session: Session,
    post: Post,
    actor: User,
    policy: Policy,
    transport,
    *,
    confirmed: bool,
    now: datetime | None = None,
) -> dict:
    if actor.role != "OWNER":
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="denied")
        session.commit()
        raise AuthError(403, "forbidden")
    if not confirmed:
        raise AuthError(400, "confirmation required")
    channel = session.get(Channel, post.channel_id)
    if channel is None:
        raise AuthError(404, "channel missing")
    sponsor = _sponsored_blocked(session, post)
    if sponsor:
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="denied", payload={"reason": sponsor})
        session.commit()
        raise AuthError(403, sponsor)
    story = session.get(Story, post.story_id)
    if post.synthetic or (story is not None and story.synthetic):
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="blocked_synthetic")
        session.commit()
        raise AuthError(409, "synthetic fixture")
    if policy.dry_run:
        add_audit(
            session,
            actor=actor.username,
            action="publish_preview",
            entity="post",
            entity_id=post.id,
            result="dry_run",
            payload={"caption_hash": post.caption_hash, "channel_id": post.channel_id},
        )
        session.commit()
        return {"mode": "dry_run", "preview": True, "caption": post.caption, "caption_hash": post.caption_hash}
    if policy.kill_switch:
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="kill_switch")
        session.commit()
        raise AuthError(403, "kill switch")
    if not policy.publish_enabled:
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="publish_disabled")
        session.commit()
        raise AuthError(403, "publish disabled")
    if not channel.publish_enabled or channel.paused:
        add_audit(session, actor=actor.username, action="publish", entity="post", entity_id=post.id, result="channel_disabled")
        session.commit()
        raise AuthError(403, "channel disabled")
    if post.review_status not in {"APPROVED", "SCHEDULED"}:
        raise AuthError(409, "post is not approved")
    outbox = (
        session.query(PublishingOutbox)
        .filter(PublishingOutbox.post_id == post.id, PublishingOutbox.state.in_(ACTIVE_OUTBOX))
        .one_or_none()
    )
    if outbox is None:
        from app.services.moderation import schedule_post

        outbox = schedule_post(session, post, actor, due=now or utcnow(), confirmed=True, now=now)
    if transport is None:
        raise AuthError(409, "no transport configured")
    return dispatch_outbox(session, outbox, transport, now=now)


def _count_today(session: Session, channel_id: str, now: datetime) -> int:
    start, end = msk_day_bounds(now)
    published = (
        session.query(PublishedMessage)
        .filter(
            PublishedMessage.channel_id == channel_id,
            PublishedMessage.published_utc >= start,
            PublishedMessage.published_utc < end,
        )
        .count()
    )
    queued = (
        session.query(PublishingOutbox)
        .filter(
            PublishingOutbox.channel_id == channel_id,
            PublishingOutbox.state.in_(("scheduled", "sending")),
            PublishingOutbox.due_utc >= start,
            PublishingOutbox.due_utc < end,
        )
        .count()
    )
    return published + queued


def scheduler_tick(
    session: Session,
    *,
    leader: bool,
    now: datetime,
    policy: Policy,
    transport=None,
    media_dir: Path | None = None,
    allowed_chat_id: str = "",
) -> TickResult:
    if not leader:
        return TickResult(False, 0, 0)
    if policy.kill_switch:
        return TickResult(True, 0, 0, blocked="kill_switch")
    scheduled = 0
    sent = 0
    moment = ensure_utc(now)
    for channel in session.query(Channel).all():
        if channel.paused:
            continue
        from app.publishing.schedule import quiet

        if quiet(moment, channel.quiet_start, channel.quiet_end):
            continue
        if slot_due(moment, list(channel.schedule_json or []), channel.timezone) and _count_today(session, channel.id, moment) < channel.daily_cap:
            post = _next_fresh_approved(session, channel.id, moment)
            if post is not None:
                from app.services.moderation import schedule_post

                owner = session.query(User).filter_by(role="OWNER").first()
                if owner is not None:
                    try:
                        schedule_post(session, post, owner, due=moment, confirmed=True, now=moment)
                        scheduled += 1
                    except AuthError:
                        session.rollback()
        if policy.network_allowed(channel.publish_enabled, channel.paused) and transport is not None:
            due_rows = (
                session.query(PublishingOutbox)
                .filter(
                    PublishingOutbox.channel_id == channel.id,
                    PublishingOutbox.state.in_(("scheduled", "retryable_failed")),
                )
                .all()
            )
            items = []
            for row in due_rows:
                post = session.get(Post, row.post_id)
                story = session.get(Story, post.story_id) if post else None
                items.append(DueItem(row.due_utc, story.published_utc if story else None, channel.id))
            chosen = select_sendable(items, moment, fresh_hours=FRESH_HOURS, limit=1)
            if not chosen:
                continue
            target_due = chosen[0].due_utc
            target = next(row for row in due_rows if row.due_utc == target_due)
            outcome = dispatch_outbox(
                session, target, transport, now=moment, media_dir=media_dir, allowed_chat_id=allowed_chat_id
            )
            if outcome.get("state") == "published":
                sent += 1
    return TickResult(True, scheduled, sent)


def _next_fresh_approved(session: Session, channel_id: str, now: datetime) -> Post | None:
    cutoff = ensure_utc(now) - timedelta(hours=FRESH_HOURS)
    rows = (
        session.query(Post)
        .join(Story, Story.id == Post.story_id)
        .filter(Post.channel_id == channel_id, Post.review_status == "APPROVED", Story.published_utc.is_not(None), Story.published_utc >= cutoff)
        .all()
    )
    for post in rows:
        active = (
            session.query(PublishingOutbox)
            .filter(PublishingOutbox.post_id == post.id, PublishingOutbox.state.in_(ACTIVE_OUTBOX + ("published",)))
            .first()
        )
        if active is None:
            return post
    return None
