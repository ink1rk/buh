#!/usr/bin/env python3
"""Notification engine and delivery policy.

The engine knows nothing about Telegram: it hands a notification to a provider.
Between an event and a notification sits the policy, which decides NOTIFY,
DIGEST or IGNORE — that is what keeps a proactive assistant from becoming a
spam bot.
"""
import datetime
import json
import time
from dataclasses import dataclass, field
from enum import Enum

from . import db
from .config import config
from .events import E, new_id


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Delivery(str, Enum):
    NOTIFY = "NOTIFY"
    DIGEST = "DIGEST"
    IGNORE = "IGNORE"


class NotificationStatus(str, Enum):
    NEW = "NEW"
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    DIGESTED = "DIGESTED"
    SUPPRESSED = "SUPPRESSED"


@dataclass
class Notification:
    type: str
    title: str
    body: str = ""
    severity: str = Severity.MEDIUM.value
    channel: str = "telegram"
    recipient: str = "owner"
    metadata: dict = field(default_factory=dict)
    correlation_id: str = None
    id: str = field(default_factory=lambda: new_id("ntf-"))
    status: str = NotificationStatus.NEW.value
    created_at: float = field(default_factory=time.time)
    sent_at: float = None

    def as_dict(self):
        return {"id": self.id, "type": self.type, "title": self.title, "body": self.body,
                "severity": self.severity, "channel": self.channel,
                "recipient": self.recipient, "metadata": self.metadata,
                "correlation_id": self.correlation_id, "status": self.status,
                "created_at": self.created_at, "sent_at": self.sent_at}


class NotificationProvider:
    channel = "base"

    def deliver(self, notification):
        raise NotImplementedError


class QueueProvider(NotificationProvider):
    """Stores notifications for a client that polls (Telegram bot, Web UI).

    The core has no Telegram token by design, so delivery is a handover: the
    notification waits in the database until the channel process picks it up.
    """

    def __init__(self, channel="telegram"):
        self.channel = channel

    def deliver(self, notification):
        return {"queued": True, "channel": self.channel}


class NotificationPolicy:
    """Phase 1 policy: severity, quiet hours and a per-source rate limit."""

    def __init__(self, cfg=None, clock=None):
        self.cfg = cfg or config.notifications
        self.clock = clock or (lambda: datetime.datetime.now(config.tz))
        self._recent: dict = {}

    def _quiet_now(self):
        hour = self.clock().hour
        start, end = self.cfg.quiet_from, self.cfg.quiet_to
        return (start <= hour or hour < end) if start > end else (start <= hour < end)

    def decide(self, notification):
        severity = Severity(notification.severity)
        if severity is Severity.CRITICAL:
            return Delivery.NOTIFY
        key = f"{notification.type}:{notification.metadata.get('source', '')}"
        now = time.time()
        if now - self._recent.get(key, 0) < self.cfg.min_interval:
            return Delivery.DIGEST
        if severity.value in self.cfg.digest_severities:
            return Delivery.DIGEST
        if self._quiet_now() and severity is not Severity.HIGH:
            return Delivery.DIGEST
        self._recent[key] = now
        return Delivery.NOTIFY


class NotificationEngine:
    def __init__(self, bus, providers=None, policy=None):
        self.bus = bus
        self.providers = {p.channel: p for p in (providers or [QueueProvider("telegram"),
                                                               QueueProvider("web")])}
        self.policy = policy or NotificationPolicy()

    def _save(self, notification):
        db.execute(
            """INSERT INTO notifications(id, type, title, body, severity, channel,
                recipient, status, metadata, correlation_id, created_at, sent_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                sent_at=excluded.sent_at, metadata=excluded.metadata""",
            (notification.id, notification.type, notification.title, notification.body,
             notification.severity, notification.channel, notification.recipient,
             notification.status,
             json.dumps(notification.metadata, ensure_ascii=False, default=str),
             notification.correlation_id, notification.created_at, notification.sent_at))
        return notification

    def notify(self, type_, title, body="", severity=Severity.MEDIUM, channel="telegram",
               metadata=None, correlation_id=None, force=False):
        notification = Notification(type=type_, title=title, body=body,
                                    severity=Severity(severity).value, channel=channel,
                                    metadata=metadata or {}, correlation_id=correlation_id)
        decision = Delivery.NOTIFY if force else self.policy.decide(notification)
        self.bus.emit(E.NOTIFICATION_CREATED,
                      {**notification.as_dict(), "delivery": decision.value},
                      source="notifications", correlation_id=correlation_id)

        if decision is Delivery.IGNORE:
            notification.status = NotificationStatus.SUPPRESSED.value
            self._save(notification)
            self.bus.emit(E.NOTIFICATION_SUPPRESSED, notification.as_dict(),
                          source="notifications", correlation_id=correlation_id)
            return notification
        if decision is Delivery.DIGEST:
            notification.status = NotificationStatus.DIGESTED.value
            return self._save(notification)

        provider = self.providers.get(channel)
        if provider is None:
            notification.status = NotificationStatus.FAILED.value
            return self._save(notification)
        try:
            provider.deliver(notification)
            notification.status = NotificationStatus.QUEUED.value
        except Exception as e:
            notification.status = NotificationStatus.FAILED.value
            notification.metadata["error"] = str(e)
        return self._save(notification)

    # -- handover to channel processes ----------------------------------
    def pending(self, channel="telegram", limit=10):
        rows = db.query(
            "SELECT * FROM notifications WHERE channel=? AND status IN ('QUEUED','NEW')"
            " ORDER BY created_at LIMIT ?", (channel, limit))
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.get("metadata") or "{}")
            except ValueError:
                item["metadata"] = {}
            out.append(item)
        return out

    def mark_sent(self, ids):
        now = time.time()
        for notification_id in ids or []:
            db.execute("UPDATE notifications SET status=?, sent_at=? WHERE id=?",
                       (NotificationStatus.SENT.value, now, notification_id))
            self.bus.emit(E.NOTIFICATION_SENT, {"id": notification_id},
                          source="notifications")
        return len(ids or [])

    def digest(self, limit=20):
        rows = db.query("SELECT * FROM notifications WHERE status=? ORDER BY created_at"
                        " LIMIT ?", (NotificationStatus.DIGESTED.value, limit))
        return [dict(r) for r in rows]

    def history(self, limit=30):
        return [dict(r) for r in db.query(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,))]

    # -- helpers used by the action engine ------------------------------
    def approval_request(self, action):
        return self.notify(
            "action.approval", f"Требуется подтверждение: {action.type}",
            body=json.dumps(action.parameters, ensure_ascii=False)[:800],
            severity=Severity.HIGH, metadata={"action_id": action.id,
                                              "action_type": action.type,
                                              "risk": action.risk_level,
                                              "kind": "approval"},
            correlation_id=action.correlation_id, force=True)

    def action_failed(self, action):
        return self.notify(
            "action.failed", f"Не удалось выполнить: {action.type}",
            body=(action.error or "")[:500], severity=Severity.MEDIUM,
            metadata={"action_id": action.id, "kind": "action_failed"},
            correlation_id=action.correlation_id)
