#!/usr/bin/env python3
"""Episodic memory: a conversation cut into finished chunks.

An episode is one exchange with a beginning, an end and an outcome — «настройка
сервера X с Иваном». It is what makes «что мы решили по серверу» answerable
without replaying every message.
"""
import json
import time
from dataclasses import dataclass, field

from core import db
from core.events import E, new_id

GAP = 3 * 3600          # a pause this long ends an episode


@dataclass
class Episode:
    conversation_id: str
    title: str = ""
    summary: str = ""
    contact_id: str = None
    decisions: list = field(default_factory=list)
    commitments: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    started_at: float = None
    ended_at: float = None
    id: str = field(default_factory=lambda: new_id("epi-"))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self):
        return {"id": self.id, "conversation_id": self.conversation_id,
                "contact_id": self.contact_id, "title": self.title,
                "summary": self.summary, "decisions": self.decisions,
                "commitments": self.commitments, "entities": self.entities,
                "started_at": self.started_at, "ended_at": self.ended_at,
                "created_at": self.created_at, "updated_at": self.updated_at}


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except ValueError:
        return default


def _row(row):
    if row is None:
        return None
    return Episode(id=row["id"], conversation_id=row["conversation_id"],
                   contact_id=row["contact_id"], title=row["title"],
                   summary=row["summary"], decisions=_loads(row["decisions"], []),
                   commitments=_loads(row["commitments"], []),
                   entities=_loads(row["entities"], []), started_at=row["started_at"],
                   ended_at=row["ended_at"], created_at=row["created_at"],
                   updated_at=row["updated_at"])


def save(episode):
    episode.updated_at = time.time()
    db.execute(
        """INSERT INTO episodes(id, conversation_id, contact_id, title, summary,
            decisions, commitments, entities, started_at, ended_at, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET title=excluded.title, summary=excluded.summary,
            decisions=excluded.decisions, commitments=excluded.commitments,
            entities=excluded.entities, ended_at=excluded.ended_at,
            updated_at=excluded.updated_at""",
        (episode.id, episode.conversation_id, episode.contact_id, episode.title,
         episode.summary, json.dumps(episode.decisions, ensure_ascii=False),
         json.dumps(episode.commitments, ensure_ascii=False),
         json.dumps(episode.entities, ensure_ascii=False), episode.started_at,
         episode.ended_at, episode.created_at, episode.updated_at))
    return episode


def get(episode_id):
    return _row(db.one("SELECT * FROM episodes WHERE id=?", (episode_id,)))


def current(conversation_id, now=None):
    """The open episode of a conversation, if the pause was short enough."""
    now = now or time.time()
    row = db.one("SELECT * FROM episodes WHERE conversation_id=? ORDER BY ended_at DESC"
                 " LIMIT 1", (conversation_id,))
    episode = _row(row)
    if episode and (now - (episode.ended_at or episode.started_at or 0)) <= GAP:
        return episode
    return None


def upsert(conversation_id, contact_id=None, title=None, summary=None, decisions=None,
           commitments=None, entities=None, ts=None, bus=None):
    ts = ts or time.time()
    episode = current(conversation_id, ts)
    created = episode is None
    if created:
        episode = Episode(conversation_id=conversation_id, contact_id=contact_id,
                          started_at=ts)
    episode.ended_at = ts
    if title:
        episode.title = title
    if summary:
        episode.summary = summary
    if decisions:
        episode.decisions = decisions
    if commitments:
        episode.commitments = commitments
    if entities:
        episode.entities = entities
    save(episode)
    if bus:
        bus.emit(E.EPISODE_CREATED if created else E.EPISODE_UPDATED,
                 episode.as_dict(), source="episodes")
    return episode


def for_conversation(conversation_id, limit=10):
    return [_row(r) for r in db.query(
        "SELECT * FROM episodes WHERE conversation_id=? ORDER BY started_at DESC LIMIT ?",
        (conversation_id, limit))]


def for_contact(contact_id, limit=10):
    return [_row(r) for r in db.query(
        "SELECT * FROM episodes WHERE contact_id=? ORDER BY started_at DESC LIMIT ?",
        (contact_id, limit))]


def delete(episode_id):
    db.execute("DELETE FROM episodes WHERE id=?", (episode_id,))
    return True
