#!/usr/bin/env python3
"""Commitments and waiting-for-reply state.

«Пришлю конфиг завтра» is a promise, «пришли договор» is an expectation. Both
are extracted from conversations so the assistant can answer «что я обещал» and
«от кого я жду ответа» without the owner keeping it in his head.
"""
import time
from dataclasses import dataclass, field

from core import db
from core.events import E, new_id

STATUSES = ("OPEN", "DONE", "OVERDUE", "CANCELLED")
DIRECTIONS = ("I_OWE", "THEY_OWE")          # кто кому должен


@dataclass
class Commitment:
    description: str
    direction: str = "I_OWE"
    owner: str = "owner"
    counterparty_id: str = None
    due_at: float = None
    source_message_id: str = None
    conversation_id: str = None
    status: str = "OPEN"
    confidence: float = 0.6
    id: str = field(default_factory=lambda: new_id("cmt-"))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    closed_at: float = None

    def as_dict(self):
        return {"id": self.id, "owner": self.owner, "counterparty_id": self.counterparty_id,
                "direction": self.direction, "description": self.description,
                "due_at": self.due_at, "source_message_id": self.source_message_id,
                "conversation_id": self.conversation_id, "status": self.status,
                "confidence": self.confidence, "created_at": self.created_at,
                "updated_at": self.updated_at, "closed_at": self.closed_at}


def _row(row):
    if row is None:
        return None
    return Commitment(id=row["id"], owner=row["owner"],
                      counterparty_id=row["counterparty_id"], direction=row["direction"],
                      description=row["description"], due_at=row["due_at"],
                      source_message_id=row["source_message_id"],
                      conversation_id=row["conversation_id"], status=row["status"],
                      confidence=row["confidence"], created_at=row["created_at"],
                      updated_at=row["updated_at"], closed_at=row["closed_at"])


def save(commitment):
    commitment.updated_at = time.time()
    db.execute(
        """INSERT INTO commitments(id, owner, counterparty_id, direction, description,
            due_at, source_message_id, conversation_id, status, confidence,
            created_at, updated_at, closed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET description=excluded.description,
            due_at=excluded.due_at, status=excluded.status,
            confidence=excluded.confidence, updated_at=excluded.updated_at,
            closed_at=excluded.closed_at""",
        (commitment.id, commitment.owner, commitment.counterparty_id,
         commitment.direction, commitment.description, commitment.due_at,
         commitment.source_message_id, commitment.conversation_id, commitment.status,
         commitment.confidence, commitment.created_at, commitment.updated_at,
         commitment.closed_at))
    return commitment


def get(commitment_id):
    return _row(db.one("SELECT * FROM commitments WHERE id=?", (commitment_id,)))


def create(description, direction="I_OWE", counterparty_id=None, due_at=None,
           conversation_id=None, source_message_id=None, confidence=0.6, bus=None):
    description = (description or "").strip()
    if len(description) < 3:
        return None
    for existing in open_commitments(counterparty_id=counterparty_id, limit=50):
        if existing.direction == direction and _same(existing.description, description):
            return existing
    commitment = Commitment(description=description, direction=direction,
                            counterparty_id=counterparty_id, due_at=due_at,
                            conversation_id=conversation_id,
                            source_message_id=source_message_id, confidence=confidence)
    save(commitment)
    if bus:
        bus.emit(E.COMMITMENT_CREATED, commitment.as_dict(), source="commitments")
    return commitment


def _same(a, b):
    from .memory import similarity
    return similarity(a, b) >= 0.6


def open_commitments(counterparty_id=None, direction=None, limit=50):
    sql = "SELECT * FROM commitments WHERE status IN ('OPEN','OVERDUE')"
    params = []
    if counterparty_id:
        sql += " AND counterparty_id=?"
        params.append(counterparty_id)
    if direction:
        sql += " AND direction=?"
        params.append(direction)
    sql += " ORDER BY due_at IS NULL, due_at, created_at LIMIT ?"
    params.append(limit)
    return [_row(r) for r in db.query(sql, tuple(params))]


def all_commitments(status=None, limit=100):
    if status:
        rows = db.query("SELECT * FROM commitments WHERE status=? ORDER BY created_at"
                        " DESC LIMIT ?", (status, limit))
    else:
        rows = db.query("SELECT * FROM commitments ORDER BY created_at DESC LIMIT ?",
                        (limit,))
    return [_row(r) for r in rows]


def complete(commitment_id, bus=None):
    commitment = get(commitment_id)
    if commitment is None:
        return None
    commitment.status = "DONE"
    commitment.closed_at = time.time()
    save(commitment)
    if bus:
        bus.emit(E.COMMITMENT_COMPLETED, commitment.as_dict(), source="commitments")
    return commitment


def cancel(commitment_id):
    commitment = get(commitment_id)
    if commitment is None:
        return None
    commitment.status = "CANCELLED"
    commitment.closed_at = time.time()
    return save(commitment)


def mark_overdue(bus=None):
    now = time.time()
    overdue = db.query("SELECT * FROM commitments WHERE status='OPEN' AND due_at IS NOT NULL"
                       " AND due_at < ?", (now,))
    for row in overdue:
        commitment = _row(row)
        commitment.status = "OVERDUE"
        save(commitment)
        if bus:
            bus.emit(E.COMMITMENT_OVERDUE, commitment.as_dict(), source="commitments")
    return len(overdue)


def close_on_reply(conversation_id, counterparty_id, bus=None):
    """Their answer closes what we were waiting for from them."""
    closed = []
    for commitment in open_commitments(counterparty_id=counterparty_id,
                                       direction="THEY_OWE"):
        if commitment.conversation_id and commitment.conversation_id != conversation_id:
            continue
        commitment.status = "DONE"
        commitment.closed_at = time.time()
        save(commitment)
        closed.append(commitment)
        if bus:
            bus.emit(E.COMMITMENT_COMPLETED, commitment.as_dict(), source="commitments")
    return closed


def waiting_for_reply(limit=20):
    return open_commitments(direction="THEY_OWE", limit=limit)


def i_owe(limit=20):
    return open_commitments(direction="I_OWE", limit=limit)


def render(items, tz=None):
    import datetime
    lines = []
    for commitment in items:
        when = ""
        if commitment.due_at:
            stamp = datetime.datetime.fromtimestamp(commitment.due_at, tz)
            when = f" · до {stamp.strftime('%d.%m %H:%M')}"
        lines.append(f"• {commitment.description}{when}")
    return "\n".join(lines)
