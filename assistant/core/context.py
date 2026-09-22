#!/usr/bin/env python3
"""Context assembly.

The resolver gathers who is talking, what was said before, what we remember
about them and what is still owed — and nothing else. It holds no agent logic:
agents receive a Context and decide what to do with it.

Retrieval is deliberately selective. Dumping the whole memory into a prompt is
both slow and a good way to make a model hallucinate confidently.
"""
import datetime
import time
from dataclasses import dataclass, field

from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod
from domain import episodes as episodes_mod
from domain import memory as memory_mod

from .config import config
from .events import new_id


@dataclass
class Context:
    text: str = ""
    interface: str = "telegram"              # telegram | web | voice | api
    session: str = "default"
    user: dict = field(default_factory=dict)
    contact: object = None
    conversation: object = None
    recent_messages: list = field(default_factory=list)
    memories: list = field(default_factory=list)
    episodes: list = field(default_factory=list)
    open_commitments: list = field(default_factory=list)
    schedule: list = field(default_factory=list)
    intents: list = field(default_factory=list)
    correlation_id: str = field(default_factory=lambda: new_id("corr-"))
    now: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(config.tz))
    locale: str = "ru"
    permissions: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def is_private_data(self):
        return bool(self.contact or self.conversation or self.open_commitments)

    def memory_block(self, limit=8):
        return memory_mod.render(self.memories, limit)

    def history_block(self, limit=14):
        lines = []
        for message in self.recent_messages[-limit:]:
            who = "Я" if message.get("from_owner") else "Он"
            text = (message.get("text") or "").strip().replace("\n", " ")
            if text:
                lines.append(f"{who}: {text[:300]}")
        return "\n".join(lines)

    def commitments_block(self):
        mine = [c for c in self.open_commitments if c.direction == "I_OWE"]
        theirs = [c for c in self.open_commitments if c.direction == "THEY_OWE"]
        blocks = []
        if mine:
            blocks.append("Я обещал:\n" + commitments_mod.render(mine, config.tz))
        if theirs:
            blocks.append("Жду от него:\n" + commitments_mod.render(theirs, config.tz))
        return "\n".join(blocks)

    def schedule_block(self, limit=5):
        """Расписание словами, а не метками времени: модель читает его как текст."""
        if not self.schedule:
            return ""
        today = self.now.date()
        lines = []
        for event in self.schedule[:limit]:
            day = event.start.date()
            if day == today:
                when = "сегодня"
            elif (day - today).days == 1:
                when = "завтра"
            else:
                when = f"{event.start:%d.%m}"
            at = "весь день" if event.all_day else f"в {event.start:%H:%M}"
            line = f"— {when} {at}: {event.summary}"
            if event.location:
                line += f" ({event.location})"
            lines.append(line)
        return "\n".join(lines)

    def as_dict(self):
        return {"text": self.text, "interface": self.interface, "session": self.session,
                "contact": self.contact.as_dict() if self.contact else None,
                "conversation": self.conversation.as_dict() if self.conversation else None,
                "recent_messages": self.recent_messages[-10:],
                "memories": [m.as_dict() for m in self.memories],
                "episodes": [e.as_dict() for e in self.episodes],
                "commitments": [c.as_dict() for c in self.open_commitments],
                "intents": self.intents, "correlation_id": self.correlation_id,
                "now": self.now.isoformat(), "permissions": self.permissions}


class ContextResolver:
    def __init__(self, permissions=None, memory_limit=None, schedule=None):
        self.permissions = permissions
        self.memory_limit = memory_limit or config.memory.retrieval_limit
        # Расписание приходит готовым списком: резолвер не должен знать, что
        # за ним стоит сеть, и не должен ждать её при каждом ответе.
        self.schedule = schedule

    def resolve(self, text="", interface="telegram", session="default",
                conversation=None, contact=None, correlation_id=None,
                intents=None, metadata=None):
        context = Context(text=text or "", interface=interface, session=session,
                          intents=list(intents or []), metadata=metadata or {})
        if correlation_id:
            context.correlation_id = correlation_id

        context.user = {"name": config.owner_name or "владелец",
                        "gender": config.owner_gender,
                        "assistant": config.assistant_name}

        if conversation is not None:
            context.conversation = conversation
            contact = contact or (contacts_mod.get(conversation.contact_id)
                                  if conversation.contact_id else None)
            context.recent_messages = conversations_mod.as_history(conversation.id, 20)
            context.episodes = episodes_mod.for_conversation(conversation.id, 3)

        if contact is not None:
            context.contact = contact
            context.open_commitments = commitments_mod.open_commitments(
                counterparty_id=contact.id, limit=10)
            if not context.episodes:
                context.episodes = episodes_mod.for_contact(contact.id, 3)

        entity_id = contact.id if contact else None
        query = text or (context.recent_messages[-1]["text"]
                         if context.recent_messages else "")
        found = memory_mod.search(query, entity_id=entity_id, limit=self.memory_limit)
        context.memories = [m for m, _ in found]
        if entity_id:
            known = {m.id for m in context.memories}
            for memory in memory_mod.for_entity(entity_id, 5):
                if memory.id not in known:
                    context.memories.append(memory)

        if self.schedule is not None:
            try:
                context.schedule = list(self.schedule(
                    limit=config.calendar.context_events,
                    within_hours=config.calendar.horizon_days * 24))
            except Exception as e:
                # Календарь — приятное дополнение к ответу, а не его условие.
                print(f"schedule unavailable: {type(e).__name__}: {e}")

        if self.permissions:
            context.permissions = {"response_mode": config.response_mode,
                                   "policy": self.permissions.describe()}
        return context

    def for_incoming_message(self, conversation, contact, text, correlation_id=None):
        """Context for «somebody wrote to me» — the reply-suggestion path."""
        context = self.resolve(text=text, interface="telegram", conversation=conversation,
                               contact=contact, correlation_id=correlation_id)
        context.metadata["incoming"] = True
        context.metadata["received_at"] = time.time()
        return context
