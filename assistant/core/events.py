#!/usr/bin/env python3
"""Event bus.

In-process and thread-safe, which is all a modular monolith needs. The public
surface (publish / subscribe / unsubscribe) is deliberately transport-agnostic:
swapping in Redis or NATS later means replacing this class, not the callers.

Every event carries a correlation_id so a whole chain — message received,
intent detected, action requested, approved, executed — can be replayed from
the audit log.
"""
import json
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field

from . import db


def new_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:16]}"


@dataclass
class Event:
    type: str
    source: str = "core"
    payload: dict = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: new_id("corr-"))
    causation_id: str = None
    id: str = field(default_factory=lambda: new_id("evt-"))
    ts: float = field(default_factory=time.time)

    def as_dict(self):
        return {"id": self.id, "type": self.type, "source": self.source,
                "payload": self.payload, "correlation_id": self.correlation_id,
                "causation_id": self.causation_id, "ts": self.ts}

    def child(self, type_, payload=None, source=None):
        """Derive a follow-up event that keeps the chain traceable."""
        return Event(type=type_, source=source or self.source, payload=payload or {},
                     correlation_id=self.correlation_id, causation_id=self.id)


def _matches(pattern, event_type):
    if pattern in ("*", event_type):
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-1])
    return False


_SHUTDOWN = object()        # sentinel that releases a worker from the queue


class EventBus:
    def __init__(self, workers=2, persist=True):
        self._subs: list = []                 # (pattern, handler, name)
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._persist = persist
        self._workers = []
        self._stop = threading.Event()
        for i in range(workers):
            thread = threading.Thread(target=self._worker, daemon=True,
                                      name=f"eventbus-{i}")
            thread.start()
            self._workers.append(thread)

    # -- subscription ---------------------------------------------------
    def subscribe(self, pattern, handler, name=None):
        with self._lock:
            self._subs.append((pattern, handler, name or getattr(handler, "__name__", "?")))
        return handler

    def unsubscribe(self, handler):
        with self._lock:
            self._subs = [s for s in self._subs if s[1] is not handler]

    def subscribers(self, event_type=None):
        with self._lock:
            return [(p, n) for p, _, n in self._subs
                    if event_type is None or _matches(p, event_type)]

    # -- publishing -----------------------------------------------------
    def publish(self, event, persist=None):
        """Deliver synchronously; handler failures never reach the publisher."""
        self._store(event, persist)
        for handler in self._handlers_for(event.type):
            self._call(handler, event)
        return event

    def publish_async(self, event, persist=None):
        """Queue for background delivery — used on the hot path."""
        self._store(event, persist)
        self._queue.put(event)
        return event

    def emit(self, type_, payload=None, source="core", correlation_id=None,
             causation_id=None, sync=False, persist=None):
        event = Event(type=type_, source=source, payload=payload or {},
                      causation_id=causation_id,
                      **({"correlation_id": correlation_id} if correlation_id else {}))
        return self.publish(event, persist) if sync else self.publish_async(event, persist)

    def drain(self, timeout=5.0):
        """Wait until queued events are processed (tests and shutdown)."""
        deadline = time.time() + timeout
        while not self._queue.empty() and time.time() < deadline:
            time.sleep(0.01)
        self._queue.join()

    # -- internals ------------------------------------------------------
    def _handlers_for(self, event_type):
        with self._lock:
            return [h for p, h, _ in self._subs if _matches(p, event_type)]

    def _call(self, handler, event):
        try:
            handler(event)
        except Exception:
            print(f"event handler failed for {event.type}:")
            traceback.print_exc()

    def _worker(self):
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if event is _SHUTDOWN:
                    return
                for handler in self._handlers_for(event.type):
                    self._call(handler, event)
            finally:
                self._queue.task_done()

    def _store(self, event, persist):
        if not (self._persist if persist is None else persist):
            return
        try:
            db.execute(
                "INSERT OR IGNORE INTO events(id, type, source, payload, correlation_id,"
                " causation_id, ts) VALUES(?,?,?,?,?,?,?)",
                (event.id, event.type, event.source,
                 json.dumps(event.payload, ensure_ascii=False, default=str),
                 event.correlation_id, event.causation_id, event.ts))
        except Exception as e:
            print("event persist failed:", e)

    def stop(self, timeout=5.0):
        """Deliver what is already queued, then let the workers finish."""
        try:
            self.drain(timeout)
        except Exception:
            pass
        self._stop.set()
        for _ in self._workers:
            self._queue.put(_SHUTDOWN)      # wake the poll loop at once
        for thread in self._workers:
            thread.join(timeout=1.0)


# Event type catalogue — keeps producers and consumers honest.
class E:
    # telegram / messaging
    TELEGRAM_MESSAGE_RECEIVED = "telegram.message.received"
    TELEGRAM_MESSAGE_SENT = "telegram.message.sent"
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_TRANSCRIBED = "message.transcribed"
    # email
    EMAIL_RECEIVED = "email.message.received"
    EMAIL_SENT = "email.message.sent"
    EMAIL_SKIPPED = "email.message.skipped"
    # core pipeline
    INTENT_DETECTED = "intent.detected"
    RESPONSE_GENERATED = "response.generated"
    # actions
    ACTION_REQUESTED = "action.requested"
    ACTION_APPROVAL_REQUIRED = "action.approval.required"
    ACTION_APPROVED = "action.approved"
    ACTION_DENIED = "action.denied"
    ACTION_CANCELLED = "action.cancelled"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    ACTION_EXPIRED = "action.expired"
    # notifications
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_SUPPRESSED = "notification.suppressed"
    # memory / domain
    MEMORY_CANDIDATE = "memory.candidate.detected"
    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_SUPERSEDED = "memory.superseded"
    MEMORY_DELETED = "memory.deleted"
    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_RESOLVED = "contact.resolved"
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_UPDATED = "conversation.updated"
    EPISODE_CREATED = "episode.created"
    EPISODE_UPDATED = "episode.updated"
    COMMITMENT_CREATED = "commitment.created"
    COMMITMENT_COMPLETED = "commitment.completed"
    COMMITMENT_OVERDUE = "commitment.overdue"
    REPLY_SUGGESTION_CREATED = "reply.suggestion.created"
    # system
    INTEGRATION_STATUS_CHANGED = "integration.status.changed"
    SYSTEM_ALERT = "system.alert"
