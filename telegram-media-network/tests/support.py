from __future__ import annotations

from pathlib import Path

from app.core.models import Post
from app.services.accounts import create_user
from app.services.editorial import ingest_source_item
from app.services.moderation import approve_post
from tests.factories import item

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "var" / "test-media"


def seed_users(db):
    owner = create_user(db, username="owner", password="owner-password-12", role="OWNER")
    editor = create_user(db, username="editor", password="editor-password-1", role="EDITOR")
    security = create_user(db, username="secops", password="security-password", role="REVIEWER_SECURITY")
    db.commit()
    return owner, editor, security


def ingest(db, source=None, *, render: bool = False):
    return ingest_source_item(db, source or item(), render=render, media_dir=MEDIA)


def approved_post(db, source=None) -> tuple[Post, object, object]:
    owner, editor, _security = seed_users(db)
    result = ingest(db, source)
    assert result.post_id, (result.status, result.blocked_reason, result.score)
    post = db.get(Post, result.post_id)
    approve_post(db, post, editor, confirmed=True)
    db.refresh(post)
    return post, owner, editor
