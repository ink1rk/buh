#!/usr/bin/env python3
"""Conversations and messages.

A conversation is a thread with a person on some platform; a message belongs to
a conversation and may be a transcribed voice note. Nothing here calls a
messaging API — integrations push messages in, the domain stores and summarises
them.
"""
import json
import time
from dataclasses import dataclass, field

from core import db
from core.events import E, new_id

MESSAGE_TYPES = ("TEXT", "VOICE", "IMAGE", "DOCUMENT", "VIDEO", "SYSTEM")


@dataclass
class Message:
    conversation_id: str
    text: str
    sender_type: str = "CONTACT"          # CONTACT | OWNER | ASSISTANT
    sender_id: str = None
    external_id: str = None
    message_type: str = "TEXT"
    transcription: str = None
    ts: float = field(default_factory=time.time)
    reply_to: str = None
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("msg-"))

    def as_dict(self):
        return {"id": self.id, "conversation_id": self.conversation_id,
                "external_id": self.external_id, "sender_id": self.sender_id,
                "sender_type": self.sender_type, "text": self.text,
                "message_type": self.message_type, "transcription": self.transcription,
                "ts": self.ts, "reply_to": self.reply_to, "metadata": self.metadata}


@dataclass
class Conversation:
    platform: str
    external_id: str
    contact_id: str = None
    title: str = None
    status: str = "ACTIVE"
    summary: str = None
    summary_updated_at: float = None
    id: str = field(default_factory=lambda: new_id("cnv-"))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_message_at: float = None

    def as_dict(self):
        return {"id": self.id, "platform": self.platform, "external_id": self.external_id,
                "contact_id": self.contact_id, "title": self.title, "status": self.status,
                "summary": self.summary, "summary_updated_at": self.summary_updated_at,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "last_message_at": self.last_message_at}


def _conv(row):
    if row is None:
        return None
    return Conversation(id=row["id"], platform=row["platform"],
                        external_id=row["external_id"], contact_id=row["contact_id"],
                        title=row["title"], status=row["status"], summary=row["summary"],
                        summary_updated_at=row["summary_updated_at"],
                        created_at=row["created_at"], updated_at=row["updated_at"],
                        last_message_at=row["last_message_at"])


def _msg(row):
    if row is None:
        return None
    try:
        metadata = json.loads(row["metadata"] or "{}")
    except ValueError:
        metadata = {}
    return Message(id=row["id"], conversation_id=row["conversation_id"],
                   external_id=row["external_id"], sender_id=row["sender_id"],
                   sender_type=row["sender_type"], text=row["text"],
                   message_type=row["message_type"], transcription=row["transcription"],
                   ts=row["ts"], reply_to=row["reply_to"], metadata=metadata)


def save_conversation(conversation):
    conversation.updated_at = time.time()
    db.execute(
        """INSERT INTO conversations(id, platform, external_id, contact_id, title,
            status, summary, summary_updated_at, created_at, updated_at, last_message_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET contact_id=excluded.contact_id,
            title=excluded.title, status=excluded.status, summary=excluded.summary,
            summary_updated_at=excluded.summary_updated_at,
            updated_at=excluded.updated_at, last_message_at=excluded.last_message_at""",
        (conversation.id, conversation.platform, conversation.external_id,
         conversation.contact_id, conversation.title, conversation.status,
         conversation.summary, conversation.summary_updated_at, conversation.created_at,
         conversation.updated_at, conversation.last_message_at))
    return conversation


def get_or_create(platform, external_id, contact_id=None, title=None, bus=None):
    row = db.one("SELECT * FROM conversations WHERE platform=? AND external_id=?",
                 (platform, str(external_id)))
    if row is not None:
        conversation = _conv(row)
        changed = False
        if contact_id and conversation.contact_id != contact_id:
            conversation.contact_id, changed = contact_id, True
        if title and conversation.title != title:
            conversation.title, changed = title, True
        if changed:
            save_conversation(conversation)
        return conversation
    conversation = Conversation(platform=platform, external_id=str(external_id),
                                contact_id=contact_id, title=title)
    save_conversation(conversation)
    if bus:
        bus.emit(E.CONVERSATION_CREATED, conversation.as_dict(), source="conversations")
    return conversation


def get(conversation_id):
    return _conv(db.one("SELECT * FROM conversations WHERE id=?", (conversation_id,)))


def recent(limit=30):
    return [_conv(r) for r in db.query(
        "SELECT * FROM conversations ORDER BY last_message_at DESC NULLS LAST LIMIT ?",
        (limit,))]


def by_contact(contact_id, limit=10):
    return [_conv(r) for r in db.query(
        "SELECT * FROM conversations WHERE contact_id=? ORDER BY last_message_at DESC"
        " LIMIT ?", (contact_id, limit))]


def add_message(message, bus=None):
    """Idempotent on (conversation_id, external_id) — Telegram retries updates."""
    if message.external_id:
        existing = db.one(
            "SELECT * FROM conv_messages WHERE conversation_id=? AND external_id=?",
            (message.conversation_id, str(message.external_id)))
        if existing is not None:
            return _msg(existing), False
    db.execute(
        """INSERT INTO conv_messages(id, conversation_id, external_id, sender_id,
            sender_type, text, message_type, transcription, ts, reply_to, metadata)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (message.id, message.conversation_id,
         str(message.external_id) if message.external_id else None,
         message.sender_id, message.sender_type, message.text, message.message_type,
         message.transcription, message.ts, message.reply_to,
         json.dumps(message.metadata, ensure_ascii=False, default=str)))
    db.execute("UPDATE conversations SET last_message_at=?, updated_at=? WHERE id=?",
               (message.ts, time.time(), message.conversation_id))
    if bus:
        bus.emit(E.MESSAGE_RECEIVED, message.as_dict(), source="conversations")
        if message.message_type == "VOICE" and message.transcription:
            bus.emit(E.MESSAGE_TRANSCRIBED,
                     {"message_id": message.id, "text": message.transcription},
                     source="conversations")
    return message, True


def get_message(message_id):
    return _msg(db.one("SELECT * FROM conv_messages WHERE id=?", (message_id,)))


def messages(conversation_id, limit=40, before=None):
    sql = "SELECT * FROM conv_messages WHERE conversation_id=?"
    params = [conversation_id]
    if before:
        sql += " AND ts < ?"
        params.append(before)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = db.query(sql, tuple(params))
    return [_msg(r) for r in reversed(rows)]


def as_history(conversation_id, limit=20):
    """Plain dicts for prompts: who wrote what, oldest first."""
    return [{"from_owner": m.sender_type in ("OWNER", "ASSISTANT"),
             "text": m.transcription or m.text, "ts": m.ts,
             "type": m.message_type}
            for m in messages(conversation_id, limit)]


def set_summary(conversation_id, summary, bus=None):
    db.execute("UPDATE conversations SET summary=?, summary_updated_at=? WHERE id=?",
               (summary, time.time(), conversation_id))
    if bus:
        bus.emit(E.CONVERSATION_UPDATED,
                 {"conversation_id": conversation_id, "summary": summary},
                 source="conversations")
    return summary


def delete(conversation_id):
    """Забыть переписку целиком: осиротевшие эпизоды и подсказки — тоже утечка."""
    messages = [row["id"] for row in db.query(
        "SELECT id FROM conv_messages WHERE conversation_id=?", (conversation_id,))]
    for message_id in messages:
        db.execute("DELETE FROM memories WHERE source_id=?", (message_id,))
    db.execute("DELETE FROM conv_messages WHERE conversation_id=?", (conversation_id,))
    db.execute("DELETE FROM episodes WHERE conversation_id=?", (conversation_id,))
    db.execute("DELETE FROM commitments WHERE conversation_id=?", (conversation_id,))
    db.execute("DELETE FROM reply_suggestions WHERE conversation_id=?",
               (conversation_id,))
    db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return True
