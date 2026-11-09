from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.models import Post, PublishingOutbox, Story, StoryLink


def pilot_report(session: Session, *, window_days: int = 14) -> dict:
    """Quality counts from the database. A person signs this; the program does not."""
    stories = session.query(func.count(Story.id)).scalar() or 0
    blocked = session.query(func.count(Story.id)).filter(Story.hard_block_reason != "").scalar() or 0
    archived = session.query(func.count(Story.id)).filter(Story.status == "ARCHIVED").scalar() or 0
    needs_review = session.query(func.count(Story.id)).filter(Story.status == "NEEDS_REVIEW").scalar() or 0
    duplicates = session.query(func.count(StoryLink.id)).filter(StoryLink.relation == "duplicate").scalar() or 0
    posts = session.query(func.count(Post.id)).scalar() or 0
    published = session.query(func.count(PublishingOutbox.id)).filter(PublishingOutbox.state == "published").scalar() or 0
    return {
        "window_days": window_days,
        "stories": int(stories),
        "blocked": int(blocked),
        "archived": int(archived),
        "needs_review": int(needs_review),
        "duplicates": int(duplicates),
        "posts": int(posts),
        "published_outbox": int(published),
        "sign_off": None,
        "sign_off_status": "BLOCKED",
        "reason": "Нужна подпись человека-редактора. Программа не ставит её сама.",
    }
