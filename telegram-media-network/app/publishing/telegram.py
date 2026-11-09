from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class AmbiguousTimeout(Exception):
    """The request may have reached Telegram. Do not send it again automatically."""


class DeliveryRejected(Exception):
    """The request was refused before acceptance."""


@dataclass
class TgResult:
    status: int
    message_id: str | None = None
    retry_after: int | None = None
    description: str = ""


@dataclass
class SpyTransport:
    calls: list[dict] = field(default_factory=list)

    def send_photo(self, payload: dict) -> TgResult:
        self.calls.append(payload)
        raise AssertionError("telegram transport was called")


class ScriptedTransport:
    def __init__(self, script: list[TgResult | Exception]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def send_photo(self, payload: dict) -> TgResult:
        self.calls.append({"chat_id": payload.get("chat_id"), "caption_hash": payload.get("caption_hash")})
        event = self.script.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


class HttpxTelegramTransport:
    """Live Bot API client. Constructed only when a real send is authorized."""

    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        if not token:
            raise RuntimeError("telegram token is empty")
        self._token = token
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, read=20.0))

    def send_photo(self, payload: dict) -> TgResult:
        url = f"https://api.telegram.org/bot{self._token}/sendPhoto"
        data = {
            "chat_id": payload["chat_id"],
            "caption": payload["caption"],
        }
        files = {"photo": ("card.jpg", payload["photo"], "image/jpeg")}
        try:
            response = self._client.post(url, data=data, files=files)
        except httpx.TimeoutException as exc:
            raise AmbiguousTimeout("timeout after request") from exc
        except httpx.TransportError as exc:
            raise DeliveryRejected("transport") from exc
        retry_after = None
        description = ""
        message_id = None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if isinstance(body, dict):
            description = str(body.get("description") or "")
            params = body.get("parameters") or {}
            if isinstance(params, dict) and params.get("retry_after") is not None:
                retry_after = int(params["retry_after"])
            result = body.get("result") or {}
            if isinstance(result, dict) and result.get("message_id") is not None:
                message_id = str(result["message_id"])
        if response.status_code == 429 and retry_after is None:
            header = response.headers.get("retry-after")
            if header:
                retry_after = int(header)
        return TgResult(response.status_code, message_id=message_id, retry_after=retry_after, description=description)
