"""R7 regressions. HTTP and Telegram here are fakes. Nothing in this file is a live check."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from app.adapters.http_client import HttpResult
from app.adapters.parse import parse_github_release, parse_github_search
from app.core.db import make_session_factory
from app.core.models import Channel, MediaAsset, Post, PublishingOutbox, Source, SourceEndpointState, Story
from app.pipeline.editor import draft_post
from app.publishing.gate import RestrictedChatTransport, build_telegram_transport
from app.publishing.photo import CardError, load_card
from app.publishing.telegram import HttpxTelegramTransport, TgResult
from app.services.accounts import AuthError
from app.services.bootstrap import bootstrap
from app.services.dispatch import dispatch_outbox
from app.services.editorial import refresh_card
from app.services.licenses import reattest_licenses
from app.services.moderation import approve_post, save_post, schedule_post
from app.workers.collect import _finish, collect_once
from fastapi.testclient import TestClient
from sqlalchemy.orm.attributes import flag_modified
from tests.conftest import make_settings
from tests.factories import NOW
from tests.support import MEDIA, approved_post, ingest, seed_users

RELEASE = {
    "tag_name": "v1.2.3",
    "html_url": "https://github.com/acme/widget/releases/tag/v1.2.3",
    "published_at": "2026-11-02T00:00:00Z",
    "body": "Исправления локального запуска.",
}


def _repo(spdx: str) -> dict:
    return {
        "id": 42,
        "full_name": "acme/widget",
        "html_url": "https://github.com/acme/widget",
        "license": {"spdx_id": spdx},
    }


def _search(spdx: str) -> dict:
    return {
        "items": [
            {
                "id": 42,
                "full_name": "acme/widget",
                "html_url": "https://github.com/acme/widget",
                "fork": False,
                "archived": False,
                "created_at": "2026-11-02T00:00:00Z",
                "pushed_at": "2026-11-02T00:00:00Z",
                "description": "Local task runner.",
                "license": {"spdx_id": spdx},
            }
        ]
    }


def _promises(draft: dict) -> None:
    blob = f"{draft['title']}\n{draft['body']}"
    assert "свободн" not in blob.lower()
    assert "бесплат" not in blob.lower()
    assert "#opensource" not in draft["suggested_hashtags"] or "GitHub указывает лицензию" in draft["body"]


def test_r7_t01_proprietary_reference_is_not_open_source():
    parsed = parse_github_release(_repo("LicenseRef-Proprietary"), RELEASE, NOW)
    assert parsed.license_state == "unknown"
    drafted = draft_post(parsed, "github")
    assert drafted.blocked is False
    assert "#opensource" not in drafted.draft["suggested_hashtags"]
    _promises(drafted.draft)


def test_r7_t02_prefixed_private_id_is_not_open_source():
    parsed = parse_github_search(_search("MIT-PrivateRestricted"), NOW)[0]
    assert parsed.license_state == "unknown"
    drafted = draft_post(parsed, "github")
    assert "#opensource" not in drafted.draft["suggested_hashtags"]
    _promises(drafted.draft)


def test_r7_t03_known_spdx_matches_across_parsers():
    for spdx in ("MIT", "Apache-2.0", "GPL-3.0-only", "Apache-2.0 OR MIT", "GPL-3.0-only WITH GCC-exception-3.1"):
        release = parse_github_release(_repo(spdx), RELEASE, NOW)
        search = parse_github_search(_search(spdx), NOW)[0]
        assert release.license_state == search.license_state == "explicit_open_source"
        drafted = draft_post(release, "github")
        assert "GitHub указывает лицензию" in drafted.draft["body"]
        assert "#opensource" in drafted.draft["suggested_hashtags"]
        assert "свободн" not in drafted.draft["body"].lower()
    for spdx in ("NOASSERTION", "OTHER", "", "NotARealLicense", "MIT AND LicenseRef-Proprietary"):
        assert parse_github_release(_repo(spdx), RELEASE, NOW).license_state == "unknown"
        assert parse_github_search(_search(spdx), NOW)[0].license_state == "unknown"


def test_r7_t04_old_false_license_leaves_the_queue(db):
    story = Story(
        title="Acme Widget",
        canonical_url="https://github.com/acme/widget",
        license_state="explicit_open_source",
        license_spdx="LicenseRef-Proprietary",
        primary_channel_id="github",
        discovered_utc=NOW,
    )
    kept = Story(
        title="Kept",
        canonical_url="https://github.com/acme/kept",
        license_state="explicit_open_source",
        license_spdx="MIT",
        primary_channel_id="github",
        discovered_utc=NOW,
    )
    db.add_all([story, kept])
    db.flush()
    post = Post(
        story_id=story.id,
        channel_id="github",
        title="Acme Widget release note",
        body="Короткий разбор релиза.",
        draft_version=1,
        review_status="APPROVED",
        final_hash="abc",
        approver_ids_json=[1],
        hashtags_json=["#github", "#opensource"],
        publish_intent_id="intent",
    )
    db.add(post)
    db.flush()
    outbox = PublishingOutbox(
        post_id=post.id,
        channel_id="github",
        due_utc=NOW,
        idempotency_key="r7-license",
        state="scheduled",
    )
    db.add(outbox)
    db.commit()
    assert reattest_licenses(db) == 1
    db.refresh(story)
    db.refresh(kept)
    db.refresh(post)
    db.refresh(outbox)
    assert story.license_state == "unknown"
    assert kept.license_state == "explicit_open_source"
    assert post.review_status == "NEEDS_REVIEW"
    assert post.approver_ids_json == []
    assert "#opensource" not in post.hashtags_json
    assert "license_unconfirmed" in post.flags_json
    assert outbox.state == "cancelled"


def _ready(db, source=None):
    _owner, editor, _security = seed_users(db)
    result = ingest(db, source, render=True)
    post = db.get(Post, result.post_id)
    db.commit()
    return post, editor


def test_r7_t05_api_edit_replaces_the_card(db):
    post, _editor = _ready(db)
    settings = make_settings()
    settings.media_dir = MEDIA
    with TestClient(create_app_for(settings)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
        assert login.status_code == 200
        response = client.patch(
            f"/api/v1/posts/{post.id}",
            json={"title": "Acme Widget runner revised locally"},
            headers={"X-CSRF-Token": login.json()["csrf_token"], "If-Match": "1"},
        )
    assert response.status_code == 200
    assert response.json()["draft_version"] == 2
    _assert_fresh_card(db, post.id)


def test_r7_t06_web_edit_uses_the_same_card_rule(db):
    post, _editor = _ready(db)
    settings = make_settings()
    settings.media_dir = MEDIA
    with TestClient(create_app_for(settings)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
        response = client.post(
            f"/review/{post.id}/save",
            data={
                "csrf_token": login.json()["csrf_token"],
                "version": "1",
                "title": "Acme Widget runner revised locally",
                "body": post.body,
                "channel_id": post.channel_id,
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    _assert_fresh_card(db, post.id)


def create_app_for(settings):
    from app.main import create_app

    return create_app(settings, init_db=True)


def _assert_fresh_card(db, post_id: int) -> None:
    db.expire_all()
    post = db.get(Post, post_id)
    photo, digest = load_card(db, post, MEDIA)
    assert photo.startswith(b"\xff\xd8\xff")
    current = db.query(MediaAsset).filter_by(post_id=post.id, status="ready").one()
    assert current.draft_version == 2
    assert current.content_hash == post.final_hash
    assert current.sha256 == digest
    old = db.query(MediaAsset).filter_by(post_id=post.id, draft_version=1).one()
    assert old.status == "stale"
    assert (MEDIA / old.file_path).read_bytes() != photo


def test_r7_t05_approved_only_after_the_new_card(db):
    post, editor = _ready(db)
    save_post(
        db,
        post,
        editor,
        title="Acme Widget runner revised locally",
        body=None,
        channel_id=None,
        expected_version=1,
        media_dir=MEDIA,
    )
    db.refresh(post)
    approve_post(db, post, editor, confirmed=True)
    schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    assert db.query(PublishingOutbox).filter_by(post_id=post.id, state="scheduled").count() == 1


def test_r7_t07_failed_render_cannot_send_the_old_card(db, monkeypatch):
    post, editor = _ready(db)

    def boom(current, _channel, directory):
        partial = directory / f".post-{current.id}-v{current.draft_version}.jpg.partial"
        partial.write_bytes(b"partial")
        raise RuntimeError("render failed")

    monkeypatch.setattr("app.services.editorial.refresh_card", boom)
    save_post(db, post, editor, title="Acme Widget runner revised locally", body=None, channel_id=None, expected_version=1, media_dir=MEDIA)
    db.refresh(post)
    assert post.draft_version == 2
    assert not (MEDIA / f".post-{post.id}-v2.jpg.partial").exists()
    with pytest.raises(CardError) as card:
        load_card(db, post, MEDIA)
    assert card.value.reason == "stale_card"
    with pytest.raises(AuthError) as denied:
        approve_post(db, post, editor, confirmed=True)
    assert denied.value.detail == "stale_card"


def test_r7_t08_edit_cancels_approval_and_outbox(db):
    post, _owner, editor = approved_post(db)
    outbox = schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    target = "dev" if post.channel_id != "dev" else "infra"
    save_post(db, post, editor, title=None, body=None, channel_id=target, expected_version=post.draft_version, media_dir=MEDIA)
    db.refresh(post)
    db.refresh(outbox)
    assert post.channel_id == target
    assert post.review_status == "NEEDS_REVIEW"
    assert post.approver_ids_json == []
    assert outbox.state == "cancelled"


class _Client:
    def __init__(self, action) -> None:
        self.action = action
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        action = self.action
        if isinstance(action, Exception):
            raise action
        return action


class _Response:
    def __init__(self, status: int, payload) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _dispatch_live(db, action, later: timedelta = timedelta(minutes=5)):
    post, _owner, editor = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    db.add(refresh_card(post, channel, MEDIA))
    db.commit()
    outbox = schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    client = _Client(action)
    transport = HttpxTelegramTransport("123456:test-token", client=client)
    first = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    second = dispatch_outbox(db, outbox, transport, now=NOW + later, media_dir=MEDIA)
    return first, second, client.calls, outbox


def test_r7_t09_remote_disconnect_is_not_retried(db):
    first, second, calls, outbox = _dispatch_live(db, httpx.RemoteProtocolError("Server disconnected without sending a response"))
    assert first["state"] == "needs_reconciliation"
    assert second.get("calls") == 0
    assert calls == 1
    assert outbox.state == "needs_reconciliation"
    assert db.query(Post).filter_by(id=outbox.post_id).one().review_status == "NEEDS_RECONCILIATION"


@pytest.mark.parametrize(
    "action",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ReadError("connection closed"),
        _Response(502, {}),
        _Response(200, ValueError("not json")),
        _Response(200, {"ok": True}),
    ],
)
def test_r7_t10_uncertain_results_stay_unrepeated(db, action):
    first, second, calls, outbox = _dispatch_live(db, action)
    assert first["state"] == "needs_reconciliation"
    assert second.get("calls") == 0
    assert calls == 1
    assert outbox.state == "needs_reconciliation"


def test_r7_t10_connect_failure_is_a_definite_refusal(db):
    first, second, calls, outbox = _dispatch_live(db, httpx.ConnectError("refused"), later=timedelta(0))
    assert first["state"] == "retryable_failed"
    assert calls == 1
    assert second.get("waiting") is True
    assert outbox.state == "retryable_failed"


def test_r7_t11_confirmed_message_is_stored_once(db):
    from app.core.models import PublishedMessage

    first, second, calls, outbox = _dispatch_live(db, _Response(200, {"ok": True, "result": {"message_id": 555}}))
    assert first["message_id"] == "555"
    assert calls == 1
    assert second["state"] == "published"
    saved = db.query(PublishedMessage).one()
    assert saved.telegram_message_id == "555"


def test_r7_t12_empty_success_is_not_a_failure(db):
    assert _finish([], [], ["ok"], None)[:2] == ("ok", [])
    assert _finish([], [], ["ok"], None)[3] == "no_new_items"
    _only(db, {"github_search", "huggingface"})
    github = db.get(Source, "github_search")
    github.policy_json = {"queries": ["topic:none"], "requests_per_poll_cap": 1}
    hf = db.get(Source, "huggingface")
    hf.policy_json = {"types": ["models"], "requests_per_poll_cap": 1}
    flag_modified(github, "policy_json")
    flag_modified(hf, "policy_json")
    db.commit()

    class Transport:
        def request(self, _method, url, _headers):
            body = b'{"items":[]}' if "github" in url else b"[]"
            return HttpResult(200, {}, body, url)

    settings = make_settings()
    settings.source_mode = "live"
    report = collect_once(db, settings, transport=Transport(), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert report.errors == 0
    assert db.get(Source, "github_search").health == "ok"
    assert db.get(Source, "github_search").last_error == "no_new_items"
    assert db.get(Source, "huggingface").last_error == "no_new_items"
    assert db.get(Source, "github_search").consecutive_failures == 0


def test_r7_t13_not_modified_plus_empty_is_not_an_error(db):
    finished = _finish([], [], ["not_modified", "ok"], None)
    assert finished[0] == "ok"
    assert finished[3] == "no_new_items"
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:one", "topic:two"], "requests_per_poll_cap": 2, "query_cursor": 0}
    flag_modified(source, "policy_json")
    db.commit()

    class Transport:
        def __init__(self):
            self.headers = []

        def request(self, _method, url, headers):
            self.headers.append((url, headers.get("If-None-Match", "")))
            if "topic%3Aone" in url or "topic:one" in url:
                return HttpResult(304, {"etag": "W/one"}, b"", url)
            return HttpResult(200, {"etag": "W/two"}, b'{"items":[]}', url)

    settings = make_settings()
    settings.source_mode = "live"
    report = collect_once(db, settings, transport=Transport(), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert report.errors == 0
    assert db.get(Source, "github_search").health == "ok"
    assert db.get(Source, "github_search").last_error == "no_new_items"
    rows = db.query(SourceEndpointState).filter_by(source_id="github_search").all()
    assert {row.etag for row in rows} == {"W/one", "W/two"}


def test_r7_t14_broken_payload_is_not_success(db):
    assert _finish([], ["invalid_payload"], ["error"], None)[0] == "error"
    assert _finish([], ["500"], ["ok", "outage"], None)[0] == "partial"
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:bad"], "requests_per_poll_cap": 1}
    flag_modified(source, "policy_json")
    db.commit()

    class Transport:
        def request(self, _method, url, _headers):
            return HttpResult(200, {}, b"{", url)

    settings = make_settings()
    settings.source_mode = "live"
    report = collect_once(db, settings, transport=Transport(), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert report.errors == 1
    assert db.get(Source, "github_search").health == "error"
    source.policy_json = {"queries": ["topic:shape"], "requests_per_poll_cap": 1}
    flag_modified(source, "policy_json")
    db.commit()

    class Shape:
        def request(self, _method, url, _headers):
            return HttpResult(200, {}, b'{"message":"not a search document"}', url)

    report = collect_once(db, settings, transport=Shape(), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert report.errors == 1
    assert db.get(Source, "github_search").health == "error"


def test_r7_t15_bootstrap_keeps_runtime_progress(db, engine):
    source = db.get(Source, "github_search")
    policy = dict(source.policy_json or {})
    policy["query_cursor"] = 3
    source.policy_json = policy
    source.circuit_open = True
    source.robots_blocked = True
    flag_modified(source, "policy_json")
    db.add(SourceEndpointState(source_id="github_search", request_url="https://api.github.com/search/repositories?q=kept", etag="W/kept"))
    db.commit()
    bootstrap(db, make_settings())
    db.commit()
    factory = make_session_factory(engine)
    with factory() as other:
        bootstrap(other, make_settings())
        other.commit()
        again = other.get(Source, "github_search")
        assert again.policy_json["query_cursor"] == 3
        assert again.circuit_open is True
        assert again.robots_blocked is True
        stored = other.query(SourceEndpointState).filter_by(source_id="github_search").one()
        assert stored.etag == "W/kept"


def test_r7_t16_rss_accept_and_its_own_etag(db):
    _only(db, {"kubernetes"})
    source = db.get(Source, "kubernetes")
    source.policy_json = {"feeds": ["https://kubernetes.io/feed.xml"], "requests_per_poll_cap": 1}
    flag_modified(source, "policy_json")
    db.add(SourceEndpointState(source_id="kubernetes", request_url="https://kubernetes.io/feed.xml", etag="W/rss"))
    db.add(SourceEndpointState(source_id="kubernetes", request_url="https://example.invalid/other.xml", etag="W/other"))
    db.commit()
    seen = []

    class Transport:
        def request(self, _method, url, headers):
            seen.append(headers)
            return HttpResult(200, {"etag": "W/rss-2"}, b"<rss><channel><title>k</title></channel></rss>", url)

    settings = make_settings()
    settings.source_mode = "live"
    collect_once(db, settings, transport=Transport(), resolver=lambda _host: ["8.8.8.8"], now=NOW, force=True)
    assert len(seen) == 1
    assert seen[0]["Accept"].startswith("application/rss+xml")
    assert seen[0]["If-None-Match"] == "W/rss"
    assert "W/other" not in seen[0].values()


def test_r7_t17_shipped_flags_block_telegram(db):
    settings = make_settings()
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert settings.source_mode == "offline"
    assert build_telegram_transport(settings) is None
    inner_calls = []

    class Inner:
        def send_photo(self, payload):
            inner_calls.append(payload)
            return TgResult(200, message_id="1")

    with pytest.raises(Exception) as denied:
        RestrictedChatTransport(Inner(), "100").send_photo({"chat_id": "200", "photo": b"jpeg"})
    assert "foreign_chat" in str(denied.value)
    assert inner_calls == []


def _only(db, ids: set[str]) -> None:
    for source in db.query(Source).all():
        source.enabled = source.id in ids
    db.commit()
