#!/usr/bin/env python3
"""Каналы входящих сообщений.

Telegram и почта различаются ровно в трёх местах: как из письма или сообщения
достать человека, как назвать диалог и какое действие отправляет ответ. Всё
остальное — контекст, подсказки, обязательства, память — общее, поэтому
конвейер один, а различия собраны здесь.

Добавить мессенджер значит дописать сюда один объект, а не ещё одну копию
конвейера.
"""
from dataclasses import dataclass, field
from typing import Callable

from domain import contacts as contacts_mod

from .events import E


@dataclass(frozen=True)
class Channel:
    name: str
    platform: str                       # как канал называется в conversations
    received_event: str
    sent_event: str
    source: str                         # для журнала и политики уведомлений
    action_type: str                    # чем отправляется ответ
    resolve_contact: Callable           # payload, bus -> Contact
    conversation_key: Callable          # payload -> external_id
    title: Callable = field(default=lambda payload: payload.get("name"))
    send_parameters: Callable = None    # suggestion, text -> dict
    notification_kind: str = "incoming_message"


def _telegram_contact(payload, bus):
    return contacts_mod.upsert_from_telegram(
        str(payload.get("peer_id")), payload.get("peer_name"),
        payload.get("username"), bus=bus)


def _telegram_send(suggestion, text):
    return {"peer_id": suggestion["peer_id"], "text": text, "as_user": True}


def _email_contact(payload, bus):
    return contacts_mod.upsert_from_email(payload.get("address"),
                                          payload.get("name"), bus=bus)


def _email_send(suggestion, text):
    """Ответ уходит той же веткой: тема с «Re:» и ссылка на исходное письмо."""
    subject = (suggestion.get("subject") or "").strip()
    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return {"to": suggestion["peer_id"], "subject": subject or "Re:", "body": text,
            "in_reply_to": suggestion.get("external_message_id"),
            "account": suggestion.get("account")}


TELEGRAM = Channel(
    name="telegram", platform="telegram",
    received_event=E.TELEGRAM_MESSAGE_RECEIVED, sent_event=E.TELEGRAM_MESSAGE_SENT,
    source="telegram", action_type="send.telegram.message",
    resolve_contact=_telegram_contact,
    conversation_key=lambda payload: str(payload.get("peer_id")),
    title=lambda payload: payload.get("peer_name"),
    send_parameters=_telegram_send)

EMAIL = Channel(
    name="email", platform="email",
    received_event=E.EMAIL_RECEIVED, sent_event=E.EMAIL_SENT,
    source="email", action_type="send.email",
    resolve_contact=_email_contact,
    conversation_key=lambda payload: (payload.get("address") or "").lower(),
    title=lambda payload: payload.get("name"),
    send_parameters=_email_send,
    notification_kind="incoming_email")

REGISTRY = {channel.name: channel for channel in (TELEGRAM, EMAIL)}
BY_PLATFORM = {channel.platform: channel for channel in (TELEGRAM, EMAIL)}


def get(name):
    return REGISTRY.get(name, TELEGRAM)


def for_platform(platform):
    return BY_PLATFORM.get(platform, TELEGRAM)
