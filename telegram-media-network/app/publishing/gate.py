"""Live Telegram transport stays unwired unless every independent gate is open."""

from __future__ import annotations

import os

from app.core.config import Settings
from app.publishing.telegram import DeliveryRejected, HttpxTelegramTransport


class RestrictedChatTransport:
    """Sandbox client. A chat id other than the approved test id never reaches the network."""

    def __init__(self, inner, allowed_chat_id: str) -> None:
        self.inner = inner
        self.allowed_chat_id = str(allowed_chat_id)

    def send_photo(self, payload: dict):
        chat_id = str(payload.get("chat_id") or "")
        if chat_id != self.allowed_chat_id:
            raise DeliveryRejected("foreign_chat")
        return self.inner.send_photo(payload)


def sandbox_chat_id(settings: Settings) -> str:
    if os.environ.get("TELEGRAM_TRANSPORT", "").strip().lower() != "sandbox":
        return ""
    return str(settings.telegram_test_chat_id or "")


def build_telegram_transport(settings: Settings) -> RestrictedChatTransport | None:
    """Return a client only for an explicit sandbox. Dry-run and the kill switch keep the app offline."""
    if os.environ.get("TELEGRAM_TRANSPORT", "").strip().lower() != "sandbox":
        return None
    if settings.dry_run or settings.global_kill_switch or not settings.publish_enabled:
        return None
    if not settings.telegram_bot_token or not settings.telegram_test_chat_id:
        return None
    return RestrictedChatTransport(HttpxTelegramTransport(settings.telegram_bot_token), settings.telegram_test_chat_id)
