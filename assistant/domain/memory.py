#!/usr/bin/env python3
"""Long-term memory.

Two rules shape this module. First, a guess is not a fact: everything carries
its source and confidence, and an LLM inference can never reach the confidence
of something the owner said outright. Second, memory is not an append-only log
of chat lines — a candidate is classified, deduplicated against what is already
known, checked for contradictions, and only then stored.

Storage is plain SQLite with token-overlap similarity. That is deliberate: the
truth lives in a normal table, and a vector index can later be added as an
accelerator without becoming the source of truth.
"""
import json
import math
import re
import time
from dataclasses import dataclass, field

from core import db
from core.config import config
from core.events import E, new_id

TYPES = ("FACT", "PREFERENCE", "EVENT", "RELATION", "PROCEDURE", "EPISODE")
SOURCES = ("USER_EXPLICIT", "USER_MESSAGE", "TELEGRAM", "EMAIL", "CALENDAR",
           "TOOL_RESULT", "LLM_INFERENCE")
STATUSES = ("ACTIVE", "SUPERSEDED", "ARCHIVED", "DELETED", "CONFLICT")

# How much a source may be trusted before anything else is considered.
SOURCE_TRUST = {"USER_EXPLICIT": 1.0, "USER_MESSAGE": 0.85, "TOOL_RESULT": 0.8,
                "CALENDAR": 0.8, "EMAIL": 0.7, "TELEGRAM": 0.7, "LLM_INFERENCE": 0.5}

STOPWORDS = {"это", "как", "что", "для", "или", "над", "под", "при", "про", "его",
             "она", "они", "мне", "меня", "тебя", "себя", "уже", "ещё", "еще", "был",
             "была", "были", "быть", "есть", "того", "тоже", "так", "там", "тут",
             "весь", "всё", "все", "нет", "да", "не", "и", "в", "на", "с", "у", "о"}

NEGATION = re.compile(r"\b(не|больше не|перестал|уволил|бросил|разлюбил|отменил)\b",
                      re.IGNORECASE)


@dataclass
class Memory:
    type: str
    content: str
    source: str = "LLM_INFERENCE"
    source_id: str = None
    entity_id: str = None
    scope: str = "GLOBAL"
    confidence: float = 0.5
    importance: float = 0.5
    status: str = "ACTIVE"
    supersedes_id: str = None
    conflict_with: str = None
    id: str = field(default_factory=lambda: new_id("mem-"))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = None

    def as_dict(self):
        return {"id": self.id, "type": self.type, "content": self.content,
                "source": self.source, "source_id": self.source_id,
                "entity_id": self.entity_id, "scope": self.scope,
                "confidence": self.confidence, "importance": self.importance,
                "status": self.status, "supersedes_id": self.supersedes_id,
                "conflict_with": self.conflict_with, "created_at": self.created_at,
                "updated_at": self.updated_at, "expires_at": self.expires_at}


def tokens(text):
    words = re.findall(r"[\w-]{3,}", (text or "").lower().replace("ё", "е"))
    return {w for w in words if w not in STOPWORDS}


def similarity(a, b):
    """Jaccard over content words: cheap, predictable, no model required."""
    ta, tb = (a if isinstance(a, set) else tokens(a)), (b if isinstance(b, set) else tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _row(row):
    if row is None:
        return None
    memory = Memory(id=row["id"], type=row["type"], content=row["content"],
                    source=row["source"], source_id=row["source_id"],
                    entity_id=row["entity_id"], scope=row["scope"],
                    confidence=row["confidence"], importance=row["importance"],
                    status=row["status"], supersedes_id=row["supersedes_id"],
                    conflict_with=row["conflict_with"], created_at=row["created_at"],
                    updated_at=row["updated_at"], expires_at=row["expires_at"])
    return memory


def save(memory):
    memory.updated_at = time.time()
    db.execute(
        """INSERT INTO memories(id, type, content, source, source_id, entity_id, scope,
            confidence, importance, status, supersedes_id, conflict_with, tokens,
            created_at, updated_at, expires_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET content=excluded.content,
            confidence=excluded.confidence, importance=excluded.importance,
            status=excluded.status, supersedes_id=excluded.supersedes_id,
            conflict_with=excluded.conflict_with, tokens=excluded.tokens,
            updated_at=excluded.updated_at, expires_at=excluded.expires_at""",
        (memory.id, memory.type, memory.content, memory.source, memory.source_id,
         memory.entity_id, memory.scope, memory.confidence, memory.importance,
         memory.status, memory.supersedes_id, memory.conflict_with,
         json.dumps(sorted(tokens(memory.content)), ensure_ascii=False),
         memory.created_at, memory.updated_at, memory.expires_at))
    return memory


def get(memory_id):
    return _row(db.one("SELECT * FROM memories WHERE id=?", (memory_id,)))


def list_memories(type_=None, entity_id=None, status="ACTIVE", limit=100):
    sql = "SELECT * FROM memories WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if type_:
        sql += " AND type=?"
        params.append(type_)
    if entity_id:
        sql += " AND entity_id=?"
        params.append(entity_id)
    sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    return [_row(r) for r in db.query(sql, tuple(params))]


def cap_confidence(source, confidence):
    """An inference may never masquerade as something the owner stated."""
    ceiling = min(SOURCE_TRUST.get(source, 0.5),
                  config.memory.inference_confidence_cap
                  if source == "LLM_INFERENCE" else 1.0)
    return round(min(float(confidence), ceiling), 3)


def find_similar(content, type_=None, entity_id=None, threshold=None):
    threshold = threshold or config.memory.dedupe_threshold
    needle = tokens(content)
    matches = []
    for memory in list_memories(type_=type_, entity_id=entity_id, limit=500):
        score = similarity(needle, memory.content)
        if score >= threshold:
            matches.append((memory, round(score, 3)))
    matches.sort(key=lambda item: -item[1])
    return matches


def _contradicts(new_content, old_content):
    """Same subject, opposite polarity — «работает в X» vs «не работает в X»."""
    new_negative = bool(NEGATION.search(new_content))
    old_negative = bool(NEGATION.search(old_content))
    if new_negative == old_negative:
        return False
    overlap = similarity(tokens(new_content) - {"не", "больше"},
                         tokens(old_content) - {"не", "больше"})
    return overlap >= 0.4


def remember(content, type_="FACT", source="LLM_INFERENCE", source_id=None,
             entity_id=None, confidence=0.5, importance=0.5, scope="GLOBAL",
             expires_at=None, bus=None):
    """The write pipeline: validate → dedupe → conflict check → store/update."""
    content = re.sub(r"\s+", " ", (content or "").strip())
    if len(content) < 4 or type_ not in TYPES:
        return None, "rejected"
    confidence = cap_confidence(source, confidence)
    if confidence < config.memory.min_confidence:
        return None, "low_confidence"

    candidate = Memory(type=type_, content=content, source=source, source_id=source_id,
                       entity_id=entity_id, confidence=confidence,
                       importance=importance, scope=scope, expires_at=expires_at)

    # 1. Contradiction with what we already believe.
    for memory in list_memories(type_=type_, entity_id=entity_id, limit=300):
        if not _contradicts(content, memory.content):
            continue
        if confidence >= memory.confidence:
            candidate.supersedes_id = memory.id
            memory.status = "SUPERSEDED"
            save(memory)
            save(candidate)
            if bus:
                bus.emit(E.MEMORY_SUPERSEDED,
                         {"old": memory.as_dict(), "new": candidate.as_dict()},
                         source="memory")
                bus.emit(E.MEMORY_CREATED, candidate.as_dict(), source="memory")
            return candidate, "superseded"
        candidate.status = "CONFLICT"
        candidate.conflict_with = memory.id
        save(candidate)
        if bus:
            bus.emit(E.MEMORY_CREATED, candidate.as_dict(), source="memory")
        return candidate, "conflict"

    # 2. Near-duplicate: reinforce instead of multiplying near-identical truths.
    duplicates = find_similar(content, type_=type_, entity_id=entity_id)
    if duplicates:
        existing, score = duplicates[0]
        existing.confidence = round(min(1.0, max(existing.confidence, confidence) + 0.05), 3)
        existing.importance = max(existing.importance, importance)
        if len(content) > len(existing.content) and source != "LLM_INFERENCE":
            existing.content = content
        save(existing)
        if bus:
            bus.emit(E.MEMORY_UPDATED, {**existing.as_dict(), "similarity": score},
                     source="memory")
        return existing, "reinforced"

    save(candidate)
    if bus:
        bus.emit(E.MEMORY_CREATED, candidate.as_dict(), source="memory")
    return candidate, "created"


def update(memory_id, **fields):
    memory = get(memory_id)
    if memory is None:
        return None
    for key, value in fields.items():
        if hasattr(memory, key) and value is not None:
            setattr(memory, key, value)
    return save(memory)


def archive(memory_id, bus=None):
    memory = update(memory_id, status="ARCHIVED")
    if memory and bus:
        bus.emit(E.MEMORY_UPDATED, memory.as_dict(), source="memory")
    return memory


def delete(memory_id, bus=None):
    """Hard delete: a «forget this» that leaves the row behind is a lie."""
    db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    if bus:
        bus.emit(E.MEMORY_DELETED, {"id": memory_id}, source="memory")
    return True


def search(query, entity_id=None, limit=10, types=None):
    """Rank by overlap, entity, recency, importance and confidence together."""
    needle = tokens(query)
    now = time.time()
    scored = []
    for memory in list_memories(entity_id=None, limit=800):
        if types and memory.type not in types:
            continue
        if memory.expires_at and memory.expires_at < now:
            continue
        overlap = similarity(needle, memory.content) if needle else 0.0
        entity_bonus = 0.25 if (entity_id and memory.entity_id == entity_id) else 0.0
        age_days = max((now - (memory.updated_at or now)) / 86400, 0)
        recency = math.exp(-age_days / 45)
        score = (overlap * 0.45 + entity_bonus + memory.importance * 0.15
                 + memory.confidence * 0.1 + recency * 0.1)
        if memory.status == "CONFLICT":
            score *= 0.5
        if score > 0.08:
            scored.append((memory, round(score, 3)))
    scored.sort(key=lambda item: -item[1])
    return scored[:limit]


def for_entity(entity_id, limit=10):
    memories = list_memories(entity_id=entity_id, limit=limit * 3)
    memories.sort(key=lambda m: (-m.importance, -(m.updated_at or 0)))
    return memories[:limit]


def render(memories, limit=10):
    """Compact text block for prompts."""
    lines = []
    for item in memories[:limit]:
        memory = item[0] if isinstance(item, tuple) else item
        mark = "?" if memory.source == "LLM_INFERENCE" or memory.confidence < 0.6 else "-"
        lines.append(f"{mark} [{memory.type.lower()}] {memory.content}")
    return "\n".join(lines)
