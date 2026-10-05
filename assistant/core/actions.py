#!/usr/bin/env python3
"""Action engine: the single door to the outside world.

Nothing in the assistant calls an external API directly. An agent (or the UI)
requests an action, the engine validates it, asks the permission engine whether
it may run, waits for approval if required, executes it through a provider,
stores the result and publishes events. Retries are limited to errors worth
retrying, and an idempotency key makes a duplicate request return the original
action instead of doing the work twice.
"""
import json
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

from . import db
from .config import config
from .events import E, new_id
from .permissions import Decision, RiskLevel


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


TERMINAL = (ActionStatus.SUCCESS, ActionStatus.FAILED, ActionStatus.CANCELLED,
            ActionStatus.EXPIRED)


class ValidationError(ValueError):
    """Bad parameters: never retried."""


class ProviderError(RuntimeError):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Action:
    type: str
    parameters: dict = field(default_factory=dict)
    source: str = "core"
    requested_by: str = "assistant"
    risk_level: str = RiskLevel.HIGH.value
    status: str = ActionStatus.PENDING.value
    requires_confirmation: bool = False
    idempotency_key: str = None
    correlation_id: str = field(default_factory=lambda: new_id("corr-"))
    id: str = field(default_factory=lambda: new_id("act-"))
    created_at: float = field(default_factory=time.time)
    approved_at: float = None
    executed_at: float = None
    expires_at: float = None
    attempts: int = 0
    result: dict = None
    error: str = None

    def as_dict(self):
        return {"id": self.id, "type": self.type, "source": self.source,
                "parameters": self.parameters, "risk_level": self.risk_level,
                "status": self.status, "requires_confirmation": self.requires_confirmation,
                "requested_by": self.requested_by, "idempotency_key": self.idempotency_key,
                "correlation_id": self.correlation_id, "created_at": self.created_at,
                "approved_at": self.approved_at, "executed_at": self.executed_at,
                "expires_at": self.expires_at, "attempts": self.attempts,
                "result": self.result, "error": self.error}


def _row_to_action(row):
    if row is None:
        return None
    action = Action(type=row["type"], parameters=json.loads(row["parameters"] or "{}"),
                    source=row["source"], requested_by=row["requested_by"],
                    risk_level=row["risk_level"], status=row["status"],
                    requires_confirmation=bool(row["requires_confirmation"]),
                    idempotency_key=row["idempotency_key"],
                    correlation_id=row["correlation_id"], id=row["id"],
                    created_at=row["created_at"])
    action.approved_at = row["approved_at"]
    action.executed_at = row["executed_at"]
    action.expires_at = row["expires_at"]
    action.attempts = row["attempts"] or 0
    action.result = json.loads(row["result"]) if row["result"] else None
    action.error = row["error"]
    return action


class ActionProvider:
    """Adapter to one external system. Providers never check permissions."""
    name = "base"
    action_types: tuple = ()

    def supports(self, action_type):
        return action_type in self.action_types

    def validate(self, action):
        """Raise ValidationError when parameters are unusable."""

    def execute(self, action):
        raise NotImplementedError


class ActionEngine:
    def __init__(self, bus, permissions, providers=None, notifier=None, cfg=None):
        self.bus = bus
        self.permissions = permissions
        self.providers = list(providers or [])
        self.notifier = notifier
        self.cfg = cfg or config.actions

    def register(self, provider):
        self.providers.append(provider)
        return provider

    def provider_for(self, action_type):
        for provider in self.providers:
            if provider.supports(action_type):
                return provider
        return None

    # -- persistence ----------------------------------------------------
    def _save(self, action):
        db.execute(
            """INSERT INTO actions(id, type, source, parameters, risk_level, status,
                requires_confirmation, requested_by, idempotency_key, correlation_id,
                created_at, approved_at, executed_at, expires_at, attempts, result, error)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                approved_at=excluded.approved_at, executed_at=excluded.executed_at,
                expires_at=excluded.expires_at, attempts=excluded.attempts,
                result=excluded.result, error=excluded.error""",
            (action.id, action.type, action.source,
             json.dumps(action.parameters, ensure_ascii=False, default=str),
             action.risk_level, action.status, int(action.requires_confirmation),
             action.requested_by, action.idempotency_key, action.correlation_id,
             action.created_at, action.approved_at, action.executed_at, action.expires_at,
             action.attempts,
             json.dumps(action.result, ensure_ascii=False, default=str) if action.result else None,
             action.error))
        return action

    def get(self, action_id):
        return _row_to_action(db.one("SELECT * FROM actions WHERE id=?", (action_id,)))

    def by_idempotency_key(self, key):
        if not key:
            return None
        return _row_to_action(db.one("SELECT * FROM actions WHERE idempotency_key=?", (key,)))

    def list(self, status=None, limit=50):
        if status:
            rows = db.query("SELECT * FROM actions WHERE status=? ORDER BY created_at DESC"
                            " LIMIT ?", (status, limit))
        else:
            rows = db.query("SELECT * FROM actions ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_row_to_action(r) for r in rows]

    # -- pipeline -------------------------------------------------------
    def request(self, type_, parameters, source="core", requested_by="assistant",
                correlation_id=None, idempotency_key=None, context=None):
        existing = self.by_idempotency_key(idempotency_key)
        if existing:
            return existing

        action = Action(type=type_, parameters=parameters or {}, source=source,
                        requested_by=requested_by, idempotency_key=idempotency_key,
                        **({"correlation_id": correlation_id} if correlation_id else {}))
        action.risk_level = self.permissions.risk_of(type_).value

        provider = self.provider_for(type_)
        if provider is None:
            action.status = ActionStatus.FAILED.value
            action.error = f"нет провайдера для {type_}"
            self._save(action)
            self.bus.emit(E.ACTION_FAILED, action.as_dict(), source="actions",
                          correlation_id=action.correlation_id)
            return action

        try:
            provider.validate(action)
        except ValidationError as e:
            action.status = ActionStatus.FAILED.value
            action.error = f"валидация: {e}"
            self._save(action)
            self.bus.emit(E.ACTION_FAILED, action.as_dict(), source="actions",
                          correlation_id=action.correlation_id)
            return action

        self._save(action)
        self.bus.emit(E.ACTION_REQUESTED, action.as_dict(), source="actions",
                      correlation_id=action.correlation_id)

        verdict = self.permissions.check(action, context)
        if verdict.decision is Decision.DENY:
            action.status = ActionStatus.CANCELLED.value
            action.error = f"запрещено политикой: {verdict.reason}"
            self._save(action)
            self.bus.emit(E.ACTION_DENIED, {**action.as_dict(), "verdict": verdict.as_dict()},
                          source="actions", correlation_id=action.correlation_id)
            return action

        if verdict.decision is Decision.REQUIRE_APPROVAL:
            action.status = ActionStatus.WAITING_APPROVAL.value
            action.requires_confirmation = True
            action.expires_at = time.time() + self.cfg.approval_ttl
            self._save(action)
            self.bus.emit(E.ACTION_APPROVAL_REQUIRED,
                          {**action.as_dict(), "verdict": verdict.as_dict()},
                          source="actions", correlation_id=action.correlation_id)
            if self.notifier:
                self.notifier.approval_request(action)
            return action

        return self.execute(action)

    def approve(self, action_id, actor="owner"):
        action = self.get(action_id)
        if action is None:
            raise LookupError("действие не найдено")
        if action.status != ActionStatus.WAITING_APPROVAL.value:
            return action
        if action.expires_at and time.time() > action.expires_at:
            action.status = ActionStatus.EXPIRED.value
            action.error = "срок подтверждения истёк"
            self._save(action)
            self.bus.emit(E.ACTION_EXPIRED, action.as_dict(), source="actions",
                          correlation_id=action.correlation_id)
            return action
        action.status = ActionStatus.APPROVED.value
        action.approved_at = time.time()
        self._save(action)
        self.bus.emit(E.ACTION_APPROVED, {**action.as_dict(), "actor": actor},
                      source="actions", correlation_id=action.correlation_id)
        return self.execute(action)

    def cancel(self, action_id, actor="owner", reason="отменено пользователем"):
        action = self.get(action_id)
        if action is None:
            raise LookupError("действие не найдено")
        if ActionStatus(action.status) in TERMINAL:
            return action
        action.status = ActionStatus.CANCELLED.value
        action.error = reason
        self._save(action)
        self.bus.emit(E.ACTION_CANCELLED, {**action.as_dict(), "actor": actor},
                      source="actions", correlation_id=action.correlation_id)
        return action

    def expire_stale(self):
        """Approvals must not linger: an old confirmation is not a confirmation."""
        now = time.time()
        stale = db.query("SELECT * FROM actions WHERE status=? AND expires_at IS NOT NULL"
                         " AND expires_at < ?", (ActionStatus.WAITING_APPROVAL.value, now))
        for row in stale:
            action = _row_to_action(row)
            action.status = ActionStatus.EXPIRED.value
            action.error = "срок подтверждения истёк"
            self._save(action)
            self.bus.emit(E.ACTION_EXPIRED, action.as_dict(), source="actions",
                          correlation_id=action.correlation_id)
        return len(stale)

    def execute(self, action):
        provider = self.provider_for(action.type)
        if provider is None:
            action.status = ActionStatus.FAILED.value
            action.error = f"нет провайдера для {action.type}"
            return self._save(action)

        action.status = ActionStatus.RUNNING.value
        self._save(action)

        delay = self.cfg.retry_backoff
        for attempt in range(1, self.cfg.max_attempts + 1):
            action.attempts = attempt
            try:
                result = provider.execute(action) or {}
                action.status = ActionStatus.SUCCESS.value
                action.result = result
                action.error = None
                action.executed_at = time.time()
                self._save(action)
                self.bus.emit(E.ACTION_EXECUTED, action.as_dict(), source="actions",
                              correlation_id=action.correlation_id)
                return action
            except Exception as e:
                retryable = _is_retryable(e)
                action.error = f"{type(e).__name__}: {e}"
                if retryable and attempt < self.cfg.max_attempts:
                    self._save(action)
                    time.sleep(delay)
                    delay *= self.cfg.retry_backoff
                    continue
                action.status = ActionStatus.FAILED.value
                action.executed_at = time.time()
                self._save(action)
                self.bus.emit(E.ACTION_FAILED, action.as_dict(), source="actions",
                              correlation_id=action.correlation_id)
                if self.notifier:
                    self.notifier.action_failed(action)
                return action


def _is_retryable(error):
    if isinstance(error, ProviderError):
        return error.retryable
    if isinstance(error, (ValidationError, LookupError, PermissionError)):
        return False
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError,
                          httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500 or error.response.status_code == 429
    return False
