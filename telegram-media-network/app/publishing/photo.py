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


def load_card(session: Session, post: Post, media_dir: Path) -> tuple[bytes, str]:
    asset = (
        session.query(MediaAsset)
        .filter(MediaAsset.post_id == post.id, MediaAsset.kind == "card", MediaAsset.status == "ready")
        .order_by(MediaAsset.id.desc())
        .first()
    )
    if asset is None or not asset.file_path:
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
