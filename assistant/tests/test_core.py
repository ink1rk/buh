"""Phase 1: event bus, action engine, permissions, notifications, audit."""
import time

import pytest

from core import audit, db
from core.actions import ActionEngine, ActionProvider, ActionStatus, ProviderError, ValidationError
from core.events import Event, EventBus
from core.llm import _extract_json
from core.notifications import (Delivery, NotificationEngine, NotificationPolicy,
                                Severity)
from core.permissions import Decision, PermissionEngine, RiskLevel


# --- event bus -----------------------------------------------------------
def test_publish_reaches_matching_subscribers(bus):
    seen = []
    bus.subscribe("telegram.message.received", lambda e: seen.append(e.type))
    bus.subscribe("telegram.*", lambda e: seen.append("wildcard"))
    bus.subscribe("other.event", lambda e: seen.append("nope"))

    bus.publish(Event(type="telegram.message.received", payload={"text": "hi"}))

    assert sorted(seen) == ["telegram.message.received", "wildcard"]


def test_unsubscribe_stops_delivery(bus):
    seen = []
    handler = bus.subscribe("*", lambda e: seen.append(e.id))
    bus.publish(Event(type="a.b"))
    bus.unsubscribe(handler)
    bus.publish(Event(type="a.b"))
    assert len(seen) == 1


def test_stop_delivers_what_is_still_queued():
    """Перезапуск не должен терять уже принятые события."""
    instance = EventBus(workers=1)
    seen = []
    instance.subscribe("*", lambda e: seen.append(e.type))
    instance.emit("a.b", persist=False)
    instance.stop()
    assert seen == ["a.b"]


def test_handler_failure_does_not_break_publishing(bus):
    delivered = []

    def broken(_):
        raise RuntimeError("boom")

    bus.subscribe("*", broken)
    bus.subscribe("*", lambda e: delivered.append(e.type))
    bus.publish(Event(type="x.y"))
    assert delivered == ["x.y"]


def test_events_are_persisted_with_correlation(bus):
    event = Event(type="a.b", payload={"k": 1})
    bus.publish(event)
    row = db.one("SELECT * FROM events WHERE id=?", (event.id,))
    assert row["correlation_id"] == event.correlation_id


def test_child_event_keeps_the_chain(bus):
    parent = Event(type="message.received")
    child = parent.child("intent.detected", {"intent": "news"})
    assert child.correlation_id == parent.correlation_id
    assert child.causation_id == parent.id


def test_async_publish_is_delivered(bus):
    seen = []
    bus.subscribe("*", lambda e: seen.append(e.type))
    bus.publish_async(Event(type="async.event"))
    bus.drain()
    assert seen == ["async.event"]


# --- permissions ---------------------------------------------------------
class DummyAction:
    def __init__(self, type_, parameters=None):
        self.type = type_
        self.parameters = parameters or {}


def test_low_risk_is_allowed_without_approval():
    engine = PermissionEngine()
    result = engine.check(DummyAction("create.task"))
    assert result.decision is Decision.ALLOW
    assert result.risk is RiskLevel.LOW


def test_medium_risk_requires_approval():
    engine = PermissionEngine()
    assert engine.check(DummyAction("send.telegram.message")).decision \
        is Decision.REQUIRE_APPROVAL


def test_user_confirmation_replaces_approval():
    engine = PermissionEngine()
    result = engine.check(DummyAction("send.telegram.message"),
                          {"user_confirmed": True})
    assert result.decision is Decision.ALLOW


def test_critical_stays_gated_even_when_confirmed():
    engine = PermissionEngine()
    result = engine.check(DummyAction("bank.transfer"), {"user_confirmed": True})
    assert result.decision is Decision.REQUIRE_APPROVAL


def test_unknown_action_type_is_treated_as_high_risk():
    engine = PermissionEngine()
    assert engine.risk_of("launch.rocket") is RiskLevel.HIGH


def test_trusted_peer_skips_approval():
    engine = PermissionEngine(trusted_peers={"12345"})
    action = DummyAction("send.telegram.message", {"peer_id": 12345, "text": "hi"})
    assert engine.check(action).decision is Decision.ALLOW


def test_policy_override_is_persisted():
    engine = PermissionEngine()
    engine.set_override("send.telegram.message", "DENY")
    assert PermissionEngine().check(DummyAction("send.telegram.message")).decision \
        is Decision.DENY


# --- action engine -------------------------------------------------------
class RecordingProvider(ActionProvider):
    action_types = ("send.telegram.message", "create.task")

    def __init__(self, fail_times=0, error=None):
        self.sent = []
        self.fail_times = fail_times
        self.error = error or ProviderError("temporary", retryable=True)

    def validate(self, action):
        if action.type == "send.telegram.message" and not action.parameters.get("text"):
            raise ValidationError("пустой текст")

    def execute(self, action):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error
        self.sent.append(action.parameters)
        return {"message_id": len(self.sent)}


@pytest.fixture
def engine(bus):
    provider = RecordingProvider()
    instance = ActionEngine(bus, PermissionEngine(), providers=[provider],
                            notifier=None)
    instance.test_provider = provider
    return instance


def test_low_risk_action_runs_immediately(engine):
    action = engine.request("create.task", {"title": "купить молоко"})
    assert action.status == ActionStatus.SUCCESS.value


def test_medium_risk_action_waits_for_approval(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    assert action.status == ActionStatus.WAITING_APPROVAL.value
    assert engine.test_provider.sent == []


def test_approval_executes_the_action(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    approved = engine.approve(action.id)
    assert approved.status == ActionStatus.SUCCESS.value
    assert engine.test_provider.sent == [{"peer_id": 1, "text": "привет"}]


def test_cancelled_action_never_runs(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    cancelled = engine.cancel(action.id)
    assert cancelled.status == ActionStatus.CANCELLED.value
    assert engine.test_provider.sent == []


def test_expired_approval_is_refused(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    db.execute("UPDATE actions SET expires_at=? WHERE id=?",
               (time.time() - 10, action.id))
    result = engine.approve(action.id)
    assert result.status == ActionStatus.EXPIRED.value
    assert engine.test_provider.sent == []


def test_expire_stale_marks_old_approvals(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    db.execute("UPDATE actions SET expires_at=? WHERE id=?",
               (time.time() - 1, action.id))
    assert engine.expire_stale() == 1
    assert engine.get(action.id).status == ActionStatus.EXPIRED.value


def test_idempotency_key_prevents_double_send(engine):
    first = engine.request("send.telegram.message", {"peer_id": 1, "text": "раз"},
                           idempotency_key="msg-42", context={"user_confirmed": True})
    second = engine.request("send.telegram.message", {"peer_id": 1, "text": "раз"},
                            idempotency_key="msg-42", context={"user_confirmed": True})
    assert first.id == second.id
    assert len(engine.test_provider.sent) == 1


def test_validation_failure_is_not_retried(engine):
    action = engine.request("send.telegram.message", {"peer_id": 1})
    assert action.status == ActionStatus.FAILED.value
    assert "валидация" in action.error


def test_retryable_error_is_retried_then_succeeds(bus):
    provider = RecordingProvider(fail_times=1)
    engine = ActionEngine(bus, PermissionEngine(), providers=[provider])
    engine.cfg = type(engine.cfg)(approval_ttl=600, max_attempts=3, retry_backoff=0.01)
    action = engine.request("create.task", {"title": "x"})
    assert action.status == ActionStatus.SUCCESS.value
    assert action.attempts == 2


def test_non_retryable_error_fails_once(bus):
    provider = RecordingProvider(fail_times=5,
                                 error=ProviderError("bad creds", retryable=False))
    engine = ActionEngine(bus, PermissionEngine(), providers=[provider])
    action = engine.request("create.task", {"title": "x"})
    assert action.status == ActionStatus.FAILED.value
    assert action.attempts == 1


def test_missing_provider_fails_gracefully(bus):
    engine = ActionEngine(bus, PermissionEngine(), providers=[])
    action = engine.request("call.taxi", {"to": "дом"})
    assert action.status == ActionStatus.FAILED.value
    assert "провайдера" in action.error


def test_action_chain_is_auditable(engine, bus):
    action = engine.request("send.telegram.message", {"peer_id": 1, "text": "привет"})
    engine.approve(action.id)
    bus.drain()
    events = [item["event"] for item in
              audit.timeline(correlation_id=action.correlation_id, limit=50)]
    assert "action.requested" in events
    assert "action.approved" in events
    assert "action.executed" in events


# --- notifications -------------------------------------------------------
def test_high_severity_notification_is_queued(bus):
    engine = NotificationEngine(bus)
    notification = engine.notify("test", "Заголовок", severity=Severity.HIGH)
    assert notification.status == "QUEUED"
    assert engine.pending()[0]["id"] == notification.id


def test_low_severity_goes_to_digest(bus):
    engine = NotificationEngine(bus)
    notification = engine.notify("test", "Мелочь", severity=Severity.LOW)
    assert notification.status == "DIGESTED"
    assert engine.pending() == []


def test_rate_limit_moves_repeats_to_digest(bus):
    engine = NotificationEngine(bus)
    first = engine.notify("msg", "Иван", severity=Severity.MEDIUM,
                          metadata={"source": "tg:1"})
    second = engine.notify("msg", "Иван", severity=Severity.MEDIUM,
                           metadata={"source": "tg:1"})
    assert first.status == "QUEUED"
    assert second.status == "DIGESTED"


def test_quiet_hours_hold_back_medium_notifications(bus):
    import datetime
    policy = NotificationPolicy(clock=lambda: datetime.datetime(2026, 9, 21, 2, 0))
    engine = NotificationEngine(bus, policy=policy)
    notification = engine.notify("msg", "ночью", severity=Severity.MEDIUM)
    assert notification.status == "DIGESTED"


def test_critical_breaks_through_quiet_hours(bus):
    import datetime
    policy = NotificationPolicy(clock=lambda: datetime.datetime(2026, 9, 21, 3, 0))
    engine = NotificationEngine(bus, policy=policy)
    notification = engine.notify("alert", "пожар", severity=Severity.CRITICAL)
    assert notification.status == "QUEUED"


def test_mark_sent_clears_the_queue(bus):
    engine = NotificationEngine(bus)
    notification = engine.notify("test", "t", severity=Severity.HIGH)
    engine.mark_sent([notification.id])
    assert engine.pending() == []


def test_approval_request_creates_notification(bus):
    engine = NotificationEngine(bus)

    class Fake:
        id, type, parameters = "act-1", "send.telegram.message", {"text": "hi"}
        risk_level, correlation_id = "MEDIUM", "corr-1"

    notification = engine.approval_request(Fake())
    assert notification.metadata["kind"] == "approval"
    assert notification.status == "QUEUED"


# --- llm helpers ---------------------------------------------------------
def test_json_is_extracted_from_noisy_output():
    assert _extract_json('Вот ответ: {"a": 1} — готово') == {"a": 1}
    assert _extract_json('```json\n{"b": 2}\n```') == {"b": 2}


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        _extract_json("вообще не json")
