"""Re-check stored GitHub license labels. This never publishes a post."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.models import Post, Story
from app.pipeline.spdx import classify_spdx
from app.services.moderation import ACTIVE_OUTBOX


def reattest_licenses(session: Session, *, commit: bool = True) -> int:
    """Drop unconfirmed open-source labels and pull those posts out of the queue."""
    from app.core.models import PublishingOutbox

    changed = 0
    stories = session.query(Story).filter(Story.license_state == "explicit_open_source").all()
    for story in stories:
        state, spdx = classify_spdx(story.license_spdx)
        if state == "explicit_open_source":
            continue
        story.license_state = "unknown"
        story.license_spdx = spdx
        changed += 1
        posts = session.query(Post).filter_by(story_id=story.id).all()
        for post in posts:
            post.hashtags_json = [tag for tag in (post.hashtags_json or []) if str(tag).lower() != "#opensource"]
            flags = [flag for flag in (post.flags_json or []) if flag != "license_unconfirmed"]
            flags.append("license_unconfirmed")
            post.flags_json = flags
            if post.review_status in {"APPROVED", "SCHEDULED", "SENDING", "NEEDS_RECONCILIATION"}:
                post.review_status = "NEEDS_REVIEW"
                post.approver_ids_json = []
            for row in (
                session.query(PublishingOutbox)
                .filter(PublishingOutbox.post_id == post.id, PublishingOutbox.state.in_(ACTIVE_OUTBOX))
                .all()
            ):
                row.state = "cancelled"
    if commit:
        session.commit()
    return changed
