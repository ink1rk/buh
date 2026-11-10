"""R8 regressions. Telegram stays mocked. The CISA file is a synthetic catalog."""

from __future__ import annotations

import inspect
import json
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from app.adapters.http_client import HttpResult
from app.adapters.parse import order_cisa, parse_cisa_kev, plan_cisa
from app.core.config import assert_can_boot
from app.core.db import SCHEMA_HEAD
from app.core.models import (
    Alert,
    Channel,
    Post,
    PublishedMessage,
    SourceItem,
    Story,
    StoryEvidence,
)
from app.core.security import Policy
from app.publishing.gate import build_telegram_transport
from app.publishing.telegram import (
    HttpxTelegramTransport,
    ScriptedTransport,
    SpyTransport,
    TgResult,
    parse_retry_after,
)
from app.services.bootstrap import bootstrap
from app.services.dispatch import claim_outbox, dispatch_outbox, recover_inflight, scheduler_tick
from app.services.editorial import refresh_card
from app.services.moderation import schedule_post
from app.workers.collect import collect_once
from app.workers.run import main
from sqlalchemy.orm import sessionmaker
from tests.conftest import make_settings
from tests.factories import NOW
from tests.support import MEDIA, approved_post

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "cisa_unsorted_40_NEVER_PUBLISH.json"
TOP25 = [f"CVE-2026-{number}" for number in range(990040, 990015, -1)]


class RecordingTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[str] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
        del method, headers
        self.calls.append(url)
        return HttpResult(200, {}, self.body, url)


def _only(db, ids: set[str]) -> None:
    from app.core.models import Source

    for source in db.query(Source).all():
        source.enabled = source.id in ids
        source.last_run_at = None
    db.commit()


def _ready(db):
    post, owner, editor = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    channel.chat_id = "100"
    db.add(refresh_card(post, channel, MEDIA))
    db.commit()
    outbox = schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    db.commit()
    return post, owner, outbox


def test_r8_t01_expired_lease_reconciles_under_kill_switch(db):
    post, _owner, outbox = _ready(db)
    outbox.state = "sending"
    outbox.lease_until = NOW + timedelta(seconds=30)
    post.review_status = "SENDING"
    db.commit()
    spy = SpyTransport()
    held = scheduler_tick(db, leader=True, now=NOW, policy=Policy(True, False, True, False), transport=spy)
    db.refresh(outbox)
    assert held.blocked == "kill_switch"
    assert outbox.state == "sending"
    assert spy.calls == []

    outbox.lease_until = NOW - timedelta(seconds=1)
    db.commit()
    missed = scheduler_tick(db, leader=False, now=NOW, policy=Policy(True, False, True, False), transport=spy)
    db.refresh(outbox)
    assert missed.leader is False
    assert outbox.state == "sending"

    stopped = scheduler_tick(db, leader=True, now=NOW, policy=Policy(True, False, True, False), transport=spy)
    db.refresh(outbox)
    db.refresh(post)
    assert stopped.blocked == "kill_switch"
    assert stopped.sent == 0
    assert outbox.state == "needs_reconciliation"
    assert outbox.last_error == "lease_expired_without_ack"
    assert post.review_status == "NEEDS_RECONCILIATION"
    assert db.query(Alert).filter_by(code="lease_expired").count() == 1
    assert spy.calls == []

    again = recover_inflight(db, NOW)
    assert again == 0
    assert db.query(Alert).filter_by(code="lease_expired").count() == 1
    outbox.state = "published"
    outbox.lease_until = NOW - timedelta(hours=2)
    db.commit()
    assert recover_inflight(db, NOW) == 0
    db.refresh(outbox)
    assert outbox.state == "published"


def test_r8_t02_startup_recovers_before_the_loop():
    source = inspect.getsource(main).split("lock = LeaderLock", 1)[1]
    assert source.index("recover_inflight") < source.index("while True")


def test_r8_t03_two_sessions_one_claim(db, engine):
    _post, _owner, outbox = _ready(db)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    results: list[int | None] = [None, None]

    def worker(index: int) -> None:
        session = factory()
        try:
            claimed = claim_outbox(session, outbox.id, NOW, atomic=True)
            if claimed is None:
                session.rollback()
            else:
                session.commit()
            results[index] = claimed
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(results, key=lambda value: value or 0) == [None, outbox.id]
    assert db.query(PublishedMessage).count() == 0
    db.refresh(outbox)
    assert outbox.state == "sending"


def test_r8_t04_api_and_scheduler_send_once(db, engine):
    post, owner, _outbox = _ready(db)
    channel = db.get(Channel, post.channel_id)
    channel.publish_enabled = True
    db.commit()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    transport = ScriptedTransport([TgResult(200, message_id="900"), TgResult(200, message_id="901")])
    original = transport.send_photo

    def slow(payload):
        time.sleep(0.2)
        return original(payload)

    transport.send_photo = slow
    errors: list[BaseException] = []
    outcomes: list[object] = []
    policy = Policy(False, True, False, False)

    def api_path() -> None:
        session = factory()
        try:
            from app.services.dispatch import publish_preview_or_send

            outcomes.append(
                publish_preview_or_send(
                    session,
                    session.get(Post, post.id),
                    session.get(type(owner), owner.id),
                    policy,
                    transport,
                confirmed=True,
                now=NOW,
                media_dir=MEDIA,
            )
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            session.close()

    def tick_path() -> None:
        session = factory()
        try:
            outcomes.append(scheduler_tick(session, leader=True, now=NOW, policy=policy, transport=transport, media_dir=MEDIA))
        except BaseException as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=api_path), threading.Thread(target=tick_path)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == [], outcomes
    assert len(transport.calls) == 1, outcomes
    assert db.query(PublishedMessage).count() == 1


def test_r8_t05_crash_before_ack_is_not_retried(db):
    _post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([TgResult(200, message_id="777"), TgResult(200, message_id="778")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, crash_before_commit=True, media_dir=MEDIA)
    assert result["crashed"] is True
    tick = scheduler_tick(
        db,
        leader=True,
        now=NOW + timedelta(minutes=5),
        policy=Policy(False, True, False, False),
        transport=transport,
        media_dir=MEDIA,
    )
    db.refresh(outbox)
    assert tick.sent == 0
    assert outbox.state == "needs_reconciliation"
    assert len(transport.calls) == 1
    assert db.query(PublishedMessage).count() == 0


def _catalog(order: str) -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if order == "reversed":
        payload["vulnerabilities"] = list(reversed(payload["vulnerabilities"]))
    return payload


def test_r8_t06_cisa_cap_is_independent_of_feed_order():
    forward = order_cisa(parse_cisa_kev(_catalog("forward"), NOW))
    backward = order_cisa(parse_cisa_kev(_catalog("reversed"), NOW))
    assert [item.cve_id for item in forward[:25]] == TOP25
    assert [item.cve_id for item in backward[:25]] == TOP25
    assert forward[-1].cve_id == "CVE-2026-990001"
    plan = plan_cisa(forward, NOW, set())
    assert plan["truncated"] == 15
    assert plan["queued"] == 0
    assert [item.cve_id for item in plan["archived"]] == TOP25
    assert all(item.cvss is None for item in forward)


def test_r8_t07_truncated_cve_is_archived_on_the_next_poll(db):
    _only(db, {"cisa_kev"})
    body = FIXTURE.read_bytes()
    settings = make_settings()
    settings.source_mode = "live"
    first = collect_once(db, settings, transport=RecordingTransport(body), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert first.count_total == 40
    assert first.count_archived == 25
    assert first.count_truncated == 15
    assert first.count_new == 0
    assert db.query(Post).count() == 0
    assert db.query(SourceItem).filter_by(external_id="cve:CVE-2026-990040:2026-10-10").count() == 1
    assert db.query(SourceItem).filter_by(external_id="cve:CVE-2026-990001:2026-09-01").count() == 0
    assert db.get(SourceItem, db.query(SourceItem).first().id).source_id == "cisa_kev"
    from app.core.models import Source

    assert db.get(Source, "cisa_kev").health == "partial"
    bootstrap(db, make_settings())
    db.commit()
    assert db.query(SourceItem).count() == 25

    second = collect_once(db, settings, transport=RecordingTransport(body), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert second.count_archived == 15
    oldest = db.query(Story).filter(Story.title.startswith("CVE-2026-990001")).one()
    assert oldest.status == "QUARANTINED"
    assert oldest.provenance_json["backfill"] is True
    assert oldest.provenance_json["date_added"] == "2026-09-01"
    assert oldest.published_utc is not None and oldest.published_utc.date().isoformat() == "2026-09-01"
    assert oldest.discovered_utc == NOW
    assert db.query(Post).count() == 0

    fresh = {
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-1001",
                "dateAdded": "2026-08-01",
                "vendorProject": "Example",
                "product": "Widget",
                "shortDescription": "An old catalog record for the widget parser.",
                "requiredAction": "Apply the vendor update.",
            },
            {
                "cveID": "CVE-2026-1002",
                "dateAdded": "2026-11-09",
                "vendorProject": "Example",
                "product": "Widget",
                "shortDescription": "A flaw in the widget parser.",
                "requiredAction": "Apply the vendor update.",
            },
        ]
    }
    report = collect_once(
        db,
        settings,
        transport=RecordingTransport(json.dumps(fresh).encode()),
        resolver=lambda _host: ["8.8.8.8"],
        now=NOW,
        force=True,
    )
    assert report.count_new == 1
    assert report.count_queued == 1
    assert report.count_archived == 1
    old = db.query(Story).filter(Story.title.startswith("CVE-2026-1001")).one()
    new = db.query(Story).filter(Story.title.startswith("CVE-2026-1002")).one()
    assert old.status == "ARCHIVED"
    assert old.provenance_json["backfill"] is True
    assert "событие дня" in old.summary
    assert db.query(Post).filter_by(story_id=old.id).count() == 0
    created = db.query(Post).filter_by(story_id=new.id).one()
    assert created.approvals_required == 2
    assert created.channel_id == "cyber"
    assert "каждый экземпляр" in created.body
    assert "событие дня" not in created.body
    evidence = db.query(StoryEvidence).filter_by(story_id=new.id).all()
    assert evidence and all(row.status == "extracted" and row.verified_at is None for row in evidence)


def test_r8_t08_same_payload_does_not_create_another_story(db):
    _only(db, {"cisa_kev"})
    payload = _catalog("forward")
    payload["vulnerabilities"] = payload["vulnerabilities"][-25:]
    body = json.dumps(payload).encode()
    settings = make_settings()
    settings.source_mode = "live"
    collect_once(db, settings, transport=RecordingTransport(body), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    stories = db.query(Story).count()
    posts = db.query(Post).count()
    assert stories == 25
    assert posts == 0
    again = collect_once(db, settings, transport=RecordingTransport(body), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert again.count_queued == 0
    assert again.count_archived == 0
    assert db.query(Story).count() == stories
    assert db.query(Post).count() == posts


@pytest.mark.parametrize("status", [400, 404, 422])
def test_r8_t09_permanent_client_errors_do_not_retry(db, status):
    _post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([TgResult(status, description="rejected")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    db.refresh(outbox)
    assert result["state"] == "dlq"
    assert outbox.state == "dlq"
    assert outbox.last_error == f"permanent_{status}"
    assert db.query(Alert).filter_by(code=f"telegram_{status}").count() == 1
    again = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(minutes=5), media_dir=MEDIA)
    assert again["calls"] == 0
    assert len(transport.calls) == 1


def test_r8_t10_forbidden_pauses_once(db):
    post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([TgResult(403, description="forbidden"), TgResult(200, message_id="1")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    db.refresh(outbox)
    channel = db.get(Channel, post.channel_id)
    assert result["state"] == "paused"
    assert channel.paused is True
    assert db.query(Alert).filter_by(code="telegram_403").count() == 1
    again = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(minutes=5), media_dir=MEDIA)
    assert again["calls"] == 0
    assert len(transport.calls) == 1


def test_r8_t11_rate_limit_is_bounded(db):
    _post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([TgResult(429, retry_after=17)])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    db.refresh(outbox)
    assert result["delay"] == 17
    assert outbox.attempts == 1
    waiting = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(seconds=5), media_dir=MEDIA)
    assert waiting["calls"] == 0
    huge = ScriptedTransport([TgResult(429, retry_after=999999)] * 3)
    later = NOW + timedelta(minutes=30)
    for _step in range(2):
        dispatch_outbox(db, outbox, huge, now=later, media_dir=MEDIA)
        later += timedelta(hours=2)
    last = dispatch_outbox(db, outbox, huge, now=later, media_dir=MEDIA)
    db.refresh(outbox)
    assert last["state"] == "dlq"
    assert outbox.attempts == 4
    assert len(huge.calls) == 3


def test_r8_t13_server_error_is_not_retried(db):
    _post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([TgResult(500, description="unavailable"), TgResult(200, message_id="1")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    db.refresh(outbox)
    assert result["state"] == "needs_reconciliation"
    assert outbox.request_sent is True
    again = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(minutes=10), media_dir=MEDIA)
    assert again["calls"] == 0
    assert len(transport.calls) == 1


def test_r8_t12_malformed_retry_after_stays_a_429():
    assert parse_retry_after(17) == 17
    assert parse_retry_after("17") == 17
    assert parse_retry_after(" 30 ") == 30
    assert parse_retry_after("") is None
    assert parse_retry_after("broken") is None
    assert parse_retry_after(-4) == 1
    assert parse_retry_after(0) == 1
    assert parse_retry_after(999999) == 3600
    assert parse_retry_after(True) is None
    assert parse_retry_after(None) is None

    def respond(header: str, parameter: object) -> TgResult:
        def handler(_request: httpx.Request) -> httpx.Response:
            body: dict = {"ok": False, "description": "Too Many Requests"}
            if parameter is not None:
                body["parameters"] = {"retry_after": parameter}
            return httpx.Response(429, headers={"Retry-After": header}, json=body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return HttpxTelegramTransport("fixture-token", client=client).send_photo(
            {"chat_id": "100", "caption": "card", "photo": b"jpeg"}
        )

    assert respond("17", None).retry_after == 17
    assert respond("broken", None).status == 429
    assert respond("broken", None).retry_after is None
    assert respond("broken", "invalid").status == 429
    assert respond("broken", "invalid").retry_after is None
    assert respond("", -5).retry_after == 1
    assert respond("", 10**9).retry_after == 3600


def test_r8_connect_failure_has_a_budget(db):
    from app.publishing.telegram import DeliveryRejected

    _post, _owner, outbox = _ready(db)
    transport = ScriptedTransport([DeliveryRejected("connect") for _index in range(4)])
    moment = NOW
    for _index in range(3):
        outcome = dispatch_outbox(db, outbox, transport, now=moment, media_dir=MEDIA)
        db.refresh(outbox)
        assert outcome["state"] == "retryable_failed"
        moment = outbox.due_utc + timedelta(seconds=1)
    last = dispatch_outbox(db, outbox, transport, now=moment, media_dir=MEDIA)
    db.refresh(outbox)
    assert last["state"] == "dlq"
    assert outbox.attempts == 4
    assert len(transport.calls) == 4


def test_r8_t16_shipped_flags_and_production_refusal():
    settings = make_settings()
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert settings.sponsored_enabled is False
    assert settings.source_mode == "offline"
    assert settings.llm_mode == "mock"
    assert build_telegram_transport(settings) is None
    example = (ROOT / "configs" / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "compose.dev.yaml").read_text(encoding="utf-8")
    for flag in ("DRY_RUN=true", "PUBLISH_ENABLED=false", "GLOBAL_KILL_SWITCH=true", "SPONSORED_ENABLED=false", "LLM_MODE=mock"):
        assert flag in example
    assert 'DRY_RUN: "true"' in compose
    assert 'PUBLISH_ENABLED: "false"' in compose
    assert 'GLOBAL_KILL_SWITCH: "true"' in compose
    assert "SOURCE_MODE: offline" in compose
    settings.environment = "production"
    with pytest.raises(RuntimeError, match="production"):
        assert_can_boot(settings)


def test_r8_t15_schema_head_is_additive():
    assert SCHEMA_HEAD == "0007_r11_editorial_pilot"
    names = [path.name for path in (ROOT / "alembic" / "versions").glob("*.py")]
    assert any(name.startswith("0001") for name in names)
    assert any(name.startswith("0002") for name in names)
    assert any(name.startswith("0003") for name in names)
    assert any(name.startswith("0004") for name in names)
    assert any(name.startswith("0005") for name in names)
    assert any(name.startswith("0006") for name in names)
