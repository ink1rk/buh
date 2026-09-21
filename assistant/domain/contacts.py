#!/usr/bin/env python3
"""Contacts and entity resolution.

A contact is a person, not a Telegram chat: the same human can appear as a
Telegram id, an email address and three nicknames. Resolution never guesses
silently — when «Серёга» matches two people, the caller is told to ask.

This module knows nothing about Telegram APIs; it only stores identifiers that
integrations hand over.
"""
import json
import re
import time
from dataclasses import dataclass, field

from core import db
from core.events import E, new_id

RELATIONSHIP_TYPES = ("FAMILY", "FRIEND", "COLLEAGUE", "MANAGER", "CLIENT",
                      "CONTRACTOR", "SERVICE", "UNKNOWN")

# Common Russian short forms, so «Серёга» finds «Сергей» without an LLM call.
NAME_STEMS = (("серг", ("серёг", "серег", "серый", "сергун")),
              ("алекс", ("саш", "шур", "лёх", "лех", "алекс")),
              ("дмитр", ("дим", "митя")),
              ("михаил", ("миш", "миха")),
              ("владимир", ("вов", "володь")),
              ("екатерин", ("кат", "катюш")),
              ("анастас", ("настя", "настён")),
              ("евген", ("жен", "жек")),
              ("никол", ("коля", "колян")),
              ("иван", ("вань", "ваня")),
              ("кирилл", ("кир", "кирюх")))


@dataclass
class Contact:
    display_name: str
    id: str = field(default_factory=lambda: new_id("cnt-"))
    first_name: str = None
    last_name: str = None
    aliases: list = field(default_factory=list)
    telegram_ids: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    notes: str = ""
    importance: float = 0.5
    relationship_type: str = "UNKNOWN"
    relationship_source: str = "LLM_INFERENCE"
    communication_style: dict = field(default_factory=dict)
    is_owner: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_interaction_at: float = None

    def as_dict(self):
        return {"id": self.id, "display_name": self.display_name,
                "first_name": self.first_name, "last_name": self.last_name,
                "aliases": self.aliases, "telegram_ids": self.telegram_ids,
                "emails": self.emails, "phones": self.phones, "notes": self.notes,
                "importance": self.importance, "relationship_type": self.relationship_type,
                "relationship_source": self.relationship_source,
                "communication_style": self.communication_style,
                "is_owner": self.is_owner, "created_at": self.created_at,
                "updated_at": self.updated_at,
                "last_interaction_at": self.last_interaction_at}


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except ValueError:
        return default


def _row(row):
    if row is None:
        return None
    return Contact(
        id=row["id"], display_name=row["display_name"], first_name=row["first_name"],
        last_name=row["last_name"], aliases=_loads(row["aliases"], []),
        telegram_ids=_loads(row["telegram_ids"], []), emails=_loads(row["emails"], []),
        phones=_loads(row["phones"], []), notes=row["notes"] or "",
        importance=row["importance"], relationship_type=row["relationship_type"],
        relationship_source=row["relationship_source"],
        communication_style=_loads(row["communication_style"], {}),
        is_owner=bool(row["is_owner"]), created_at=row["created_at"],
        updated_at=row["updated_at"], last_interaction_at=row["last_interaction_at"])


def save(contact):
    contact.updated_at = time.time()
    db.execute(
        """INSERT INTO contacts(id, display_name, first_name, last_name, aliases,
            telegram_ids, emails, phones, notes, importance, relationship_type,
            relationship_source, communication_style, is_owner, created_at, updated_at,
            last_interaction_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
            first_name=excluded.first_name, last_name=excluded.last_name,
            aliases=excluded.aliases, telegram_ids=excluded.telegram_ids,
            emails=excluded.emails, phones=excluded.phones, notes=excluded.notes,
            importance=excluded.importance, relationship_type=excluded.relationship_type,
            relationship_source=excluded.relationship_source,
            communication_style=excluded.communication_style,
            updated_at=excluded.updated_at,
            last_interaction_at=excluded.last_interaction_at""",
        (contact.id, contact.display_name, contact.first_name, contact.last_name,
         json.dumps(contact.aliases, ensure_ascii=False),
         json.dumps(contact.telegram_ids, ensure_ascii=False),
         json.dumps(contact.emails, ensure_ascii=False),
         json.dumps(contact.phones, ensure_ascii=False), contact.notes,
         contact.importance, contact.relationship_type, contact.relationship_source,
         json.dumps(contact.communication_style, ensure_ascii=False),
         int(contact.is_owner), contact.created_at, contact.updated_at,
         contact.last_interaction_at))
    return contact


def get(contact_id):
    return _row(db.one("SELECT * FROM contacts WHERE id=?", (contact_id,)))


def all_contacts(limit=200):
    return [_row(r) for r in db.query(
        "SELECT * FROM contacts ORDER BY last_interaction_at DESC NULLS LAST,"
        " display_name LIMIT ?", (limit,))]


def by_telegram_id(telegram_id):
    needle = f'"{telegram_id}"'
    row = db.one("SELECT * FROM contacts WHERE telegram_ids LIKE ?", (f"%{needle}%",))
    return _row(row)


def by_email(address):
    row = db.one("SELECT * FROM contacts WHERE emails LIKE ?",
                 (f"%{address.lower()}%",))
    return _row(row)


def owner():
    return _row(db.one("SELECT * FROM contacts WHERE is_owner=1"))


def upsert_from_telegram(telegram_id, display_name, username=None, bus=None):
    """Called by the Telegram integration when a message arrives."""
    contact = by_telegram_id(telegram_id)
    created = False
    if contact is None:
        contact = Contact(display_name=display_name or f"tg:{telegram_id}",
                          telegram_ids=[str(telegram_id)])
        created = True
    if display_name and contact.display_name.startswith("tg:"):
        contact.display_name = display_name
    for alias in filter(None, [username, display_name]):
        alias = alias.strip()
        if alias and alias != contact.display_name and alias not in contact.aliases:
            contact.aliases.append(alias)
    parts = (contact.display_name or "").split()
    if parts and not contact.first_name:
        contact.first_name = parts[0]
        contact.last_name = parts[1] if len(parts) > 1 else None
    contact.last_interaction_at = time.time()
    save(contact)
    if bus:
        bus.emit(E.CONTACT_CREATED if created else E.CONTACT_UPDATED,
                 contact.as_dict(), source="contacts")
    return contact


def _norm(text):
    return re.sub(r"[^\w]+", "", (text or "").lower().replace("ё", "е"))


def _stem_match(needle, candidate):
    needle, candidate = _norm(needle), _norm(candidate)
    if not needle or not candidate:
        return False
    if candidate.startswith(needle[:4]) and len(needle) >= 3:
        return True
    for stem, shorts in NAME_STEMS:
        if candidate.startswith(stem) and any(needle.startswith(s) for s in shorts):
            return True
        if needle.startswith(stem) and any(candidate.startswith(s) for s in shorts):
            return True
    return False


def resolve(query, context_contact_ids=(), limit=5):
    """Return candidates for a name. Exact identity wins; nicknames may tie."""
    text = (query or "").strip()
    if not text:
        return []
    if text.isdigit():
        found = by_telegram_id(text)
        return [(found, 1.0)] if found else []
    if "@" in text:
        found = by_email(text.lower())
        return [(found, 1.0)] if found else []

    scored = []
    for contact in all_contacts(500):
        names = [contact.display_name, contact.first_name, contact.last_name,
                 *contact.aliases]
        score = 0.0
        for name in filter(None, names):
            if _norm(name) == _norm(text):
                score = max(score, 1.0)
            elif _norm(text) and _norm(text) in _norm(name):
                score = max(score, 0.8)
            elif _stem_match(text, name):
                score = max(score, 0.7)
        if score and contact.id in context_contact_ids:
            score += 0.15                       # кого обсуждали только что
        if score:
            score += min(contact.importance, 1.0) * 0.05
            scored.append((contact, round(min(score, 1.0), 3)))
    scored.sort(key=lambda item: (-item[1], -(item[0].last_interaction_at or 0)))
    return scored[:limit]


def resolve_one(query, context_contact_ids=()):
    """(contact, candidates): contact is None when the name is ambiguous."""
    candidates = resolve(query, context_contact_ids)
    if not candidates:
        return None, []
    best_score = candidates[0][1]
    tied = [c for c, s in candidates if s >= best_score - 0.05]
    if len(tied) > 1:
        return None, candidates
    return candidates[0][0], candidates


def update_style(contact, messages):
    """Derive an observable writing style — length, formality, emoji, greetings."""
    mine = [m for m in messages if m.get("from_owner")]
    theirs = [m for m in messages if not m.get("from_owner")]
    sample = theirs or mine
    if not sample:
        return contact
    texts = [m.get("text", "") for m in sample if m.get("text")]
    if not texts:
        return contact
    avg_len = sum(len(t) for t in texts) / len(texts)
    formal = sum(1 for t in texts if re.search(r"\b(вы|вас|вам|здравствуйте|добрый день)\b",
                                               t.lower()))
    emoji = sum(1 for t in texts if re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", t))
    style = {
        "avg_length": round(avg_len),
        "length": "short" if avg_len < 80 else ("medium" if avg_len < 250 else "long"),
        "formality": "formal" if formal > len(texts) / 3 else "informal",
        "emoji": "often" if emoji > len(texts) / 3 else ("sometimes" if emoji else "rare"),
        "samples": texts[-3:],
        "updated_at": time.time(),
    }
    contact.communication_style = style
    return save(contact)


def delete(contact_id):
    """Удалить человека — значит забыть и всё, что о нём знаем."""
    from . import conversations as conversations_mod

    for row in db.query("SELECT id FROM conversations WHERE contact_id=?", (contact_id,)):
        conversations_mod.delete(row["id"])
    db.execute("DELETE FROM memories WHERE entity_id=?", (contact_id,))
    db.execute("DELETE FROM episodes WHERE contact_id=?", (contact_id,))
    db.execute("DELETE FROM commitments WHERE counterparty_id=?", (contact_id,))
    db.execute("DELETE FROM reply_suggestions WHERE contact_id=?", (contact_id,))
    db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
    return True
