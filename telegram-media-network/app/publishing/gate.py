"""Live Telegram transport stays unwired unless every independent gate is open."""

from __future__ import annotations

import os

from app.core.config import Settings
from app.publishing.telegram import HttpxTelegramTransport


def build_telegram_transport(settings: Settings) -> HttpxTelegramTransport | None:
    """Return a client only for an explicit sandbox. Dry-run and the kill switch keep the app offline."""
    if os.environ.get("TELEGRAM_TRANSPORT", "").strip().lower() != "sandbox":
        return None
    if settings.dry_run or settings.global_kill_switch or not settings.publish_enabled:
        return None
    if not settings.telegram_bot_token or not settings.telegram_test_chat_id:
        return None
    return HttpxTelegramTransport(settings.telegram_bot_token)
