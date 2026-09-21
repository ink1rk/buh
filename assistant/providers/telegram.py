#!/usr/bin/env python3
"""Telegram action provider.

Two different Telegram identities live behind one provider: the bot (talks to
the owner) and the owner's own account through the tg-user service (talks to
other people). Which one is used depends on the action parameters, and neither
is reachable from anywhere else in the core.
"""
import httpx

from core.actions import ActionProvider, ProviderError, ValidationError
from core.config import config


class TelegramActionProvider(ActionProvider):
    name = "telegram"
    action_types = ("send.telegram.message", "edit.telegram.message",
                    "delete.telegram.message")

    def __init__(self, cfg=None):
        self.cfg = cfg or config.telegram

    # -- transports -----------------------------------------------------
    def _bot(self, method, **payload):
        if not self.cfg.bot_token:
            raise ProviderError("нет токена бота", retryable=False)
        url = f"https://api.telegram.org/bot{self.cfg.bot_token}/{method}"
        try:
            with httpx.Client(proxy=self.cfg.proxy, timeout=40) as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"сеть Telegram: {e}", retryable=True) from e
        data = response.json()
        if not data.get("ok"):
            description = str(data.get("description", ""))
            retryable = "too many requests" in description.lower()
            raise ProviderError(f"Telegram: {description}", retryable=retryable)
        return data.get("result", {})

    def _user(self, path, payload):
        url = f"{self.cfg.user_service_url}{path}"
        try:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"tg-user недоступен: {e}", retryable=True) from e
        if data.get("error"):
            raise ProviderError(f"tg-user: {data['error']}", retryable=False)
        return data

    # -- ActionProvider --------------------------------------------------
    def validate(self, action):
        params = action.parameters or {}
        if action.type == "send.telegram.message":
            if not (params.get("peer_id") or params.get("chat_id")):
                raise ValidationError("нужен peer_id или chat_id")
            if not (params.get("text") or "").strip():
                raise ValidationError("пустой текст сообщения")
            if len(params["text"]) > 4096:
                raise ValidationError("сообщение длиннее 4096 символов")
        elif action.type in ("edit.telegram.message", "delete.telegram.message"):
            if not params.get("chat_id") or not params.get("message_id"):
                raise ValidationError("нужны chat_id и message_id")

    def execute(self, action):
        params = action.parameters or {}
        if action.type == "send.telegram.message":
            text = params["text"]
            # as_user: пишем от лица владельца через его аккаунт
            if params.get("as_user") or (params.get("peer_id") and not params.get("chat_id")):
                result = self._user("/send", {"peer_id": params.get("peer_id"),
                                              "text": text})
                return {"transport": "tg-user", "message_id": result.get("message_id"),
                        "peer_id": params.get("peer_id"), "text": text}
            result = self._bot("sendMessage", chat_id=params.get("chat_id"), text=text,
                               parse_mode=params.get("parse_mode", "HTML"),
                               disable_web_page_preview=True)
            return {"transport": "bot", "message_id": result.get("message_id"),
                    "chat_id": params.get("chat_id"), "text": text}
        if action.type == "edit.telegram.message":
            result = self._bot("editMessageText", chat_id=params["chat_id"],
                               message_id=params["message_id"], text=params.get("text", ""),
                               parse_mode=params.get("parse_mode", "HTML"))
            return {"transport": "bot", "message_id": result.get("message_id")}
        result = self._bot("deleteMessage", chat_id=params["chat_id"],
                           message_id=params["message_id"])
        return {"transport": "bot", "deleted": bool(result)}
