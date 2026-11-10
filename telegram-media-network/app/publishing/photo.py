"""Bytes that may be attached to a Telegram photo. An empty body is not a card."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.models import MediaAsset, Post
from app.media.renderer import inspect_image


class CardError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def matching_card(session: Session, post: Post) -> MediaAsset | None:
    return (
        session.query(MediaAsset)
        .filter(
            MediaAsset.post_id == post.id,
            MediaAsset.kind == "card",
            MediaAsset.status == "ready",
            MediaAsset.draft_version == post.draft_version,
            MediaAsset.content_hash == post.final_hash,
        )
        .order_by(MediaAsset.id.desc())
        .first()
    )


def card_gap(session: Session, post: Post) -> str:
    """Empty when no card was ever made, or the ready card matches this version."""
    if session.query(MediaAsset).filter_by(post_id=post.id, kind="card").first() is None:
        return ""
    if matching_card(session, post) is None:
        return "stale_card"
    return ""


def load_card(session: Session, post: Post, media_dir: Path) -> tuple[bytes, str]:
    asset = matching_card(session, post)
    if asset is None or not asset.file_path:
        if session.query(MediaAsset).filter_by(post_id=post.id, kind="card").first() is not None:
            raise CardError("stale_card")
        raise CardError("missing_card")
    path = Path(asset.file_path)
    if not path.is_absolute():
        path = media_dir / path
    if not path.is_file():
        raise CardError("missing_file")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if asset.sha256 and digest != asset.sha256:
        raise CardError("hash_mismatch")
    if not data.startswith(b"\xff\xd8\xff"):
        raise CardError("not_jpeg")
    inspection = inspect_image(data)
    if not inspection.ok:
        raise CardError(inspection.reason)
    return data, digest
