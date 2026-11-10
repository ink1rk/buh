"""Rework R1–R4. Every HTTP server here is local. Nothing is a real publication."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.adapters.http_client import HttpResult
from app.adapters.live_http import PinnedHTTPTransport, TransportError
from app.core.db import SCHEMA_HEAD, assert_schema_head, make_engine, prepare_database
from app.core.models import AuditEvent, Channel, MediaAsset, Post, PublishingOutbox, Source, SourceItem
from app.ops.backup import create_media_backup, restore_media_backup
from app.pipeline.editor import draft_post
from app.pipeline.llm import LocalLLMClient
from app.publishing.gate import RestrictedChatTransport
from app.publishing.telegram import ScriptedTransport, SpyTransport, TgResult
from app.services.dispatch import dispatch_outbox
from app.services.editorial import ingest_source_item, refresh_card
from app.services.moderation import schedule_post
from app.workers.collect import collect_once
from app.workers.run import collect_cycle
from tests.conftest import make_settings
from tests.factories import NOW, item
from tests.support import MEDIA, approved_post


class MapTransport:
    def __init__(self, routes: dict[str, bytes], status: int = 200) -> None:
        self.routes = routes
        self.status = status
        self.calls: list[str] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
        del method, headers
        self.calls.append(url)
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                return HttpResult(self.status, {}, body, url)
        return HttpResult(404, {}, b"", url)


def _resolver(_host: str) -> list[str]:
    return ["8.8.8.8"]


def _only(db, ids: set[str]) -> None:
    for source in db.query(Source).all():
        source.enabled = source.id in ids
        source.last_run_at = None
        source.circuit_open = False
        source.consecutive_failures = 0
    db.commit()


def _github_body() -> bytes:
    return json.dumps(
        {
            "items": [
                {
                    "id": 9100 + index,
                    "full_name": f"acme/rework-{index}",
                    "html_url": f"https://github.com/acme/rework-{index}",
                    "description": "Учебный репозиторий для повторной приёмки сборщика, не новость.",
                    "fork": False,
                    "archived": False,
                    "created_at": "2026-11-01T00:00:00Z",
                    "pushed_at": "2026-11-09T00:00:00Z",
                    "license": {"spdx_id": "Apache-2.0"},
                    "topics": [],
                }
                for index in range(1, 4)
            ]
        }
    ).encode()


def test_t01_offline_cycle_makes_no_requests(db):
    transport = MapTransport({})
    report = collect_cycle(db, make_settings(), transport=transport, resolver=_resolver, now=NOW, force=True)
    assert transport.calls == []
    assert report.requests == 0
    assert report.offline >= 1
    assert db.get(Source, "github_search").health == "offline"


def test_t02_worker_cycle_ingests_and_dedups(db):
    _only(db, {"github_search"})
    transport = MapTransport({"https://api.github.com/search/": _github_body()})
    settings = make_settings()
    settings.source_mode = "live"
    first = collect_cycle(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert first.errors == 0
    assert db.query(SourceItem).filter_by(source_id="github_search").count() >= 3
    second = collect_cycle(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert second.duplicates >= 3
    assert db.query(SourceItem).filter_by(source_id="github_search").count() == 3


def test_t03_live_without_transport_is_an_error(db):
    _only(db, {"github_search"})
    settings = make_settings()
    settings.source_mode = "live"
    report = collect_once(db, settings, transport=None, resolver=_resolver, now=NOW, force=True)
    assert report.errors == 1
    source = db.get(Source, "github_search")
    assert source.health == "error"
    assert source.health != "ok"
    assert "no HTTP transport" in source.last_error


def test_t04_github_queries_rotate(db):
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {
        "queries": ["topic:one", "topic:two", "topic:three", "topic:four", "topic:five"],
        "requests_per_poll_cap": 2,
        "query_cursor": 0,
    }
    db.commit()
    transport = MapTransport({"https://api.github.com/search/": _github_body()})
    settings = make_settings()
    settings.source_mode = "live"
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert any("topic%3Aone" in url or "topic:one" in url for url in transport.calls)
    assert any("topic%3Atwo" in url or "topic:two" in url for url in transport.calls)
    assert not any("topic%3Afive" in url or "topic:five" in url for url in transport.calls)
    transport.calls.clear()
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert any("topic%3Athree" in url or "topic:three" in url for url in transport.calls)
    assert any("topic%3Afour" in url or "topic:four" in url for url in transport.calls)


def test_t05_github_release_is_parsed(db):
    _only(db, {"github_releases"})
    source = db.get(Source, "github_releases")
    source.policy_json = {"watched_repos": ["acme/widget"], "requests_per_poll_cap": 4}
    db.commit()
    repo = {"id": 42, "full_name": "acme/widget", "html_url": "https://github.com/acme/widget", "license": {"spdx_id": "MIT"}}
    release = [{"tag_name": "v1.2.0", "html_url": "https://github.com/acme/widget/releases/tag/v1.2.0", "published_at": "2026-11-02T00:00:00Z", "body": "Учебный релиз."}]
    transport = MapTransport(
        {
            "https://api.github.com/repos/acme/widget/releases": json.dumps(release).encode(),
            "https://api.github.com/repos/acme/widget": json.dumps(repo).encode(),
        }
    )
    settings = make_settings()
    settings.source_mode = "live"
    report = collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert report.errors == 0
    stored = db.query(SourceItem).filter_by(source_id="github_releases").one()
    assert stored.external_id.startswith("github-release:")
    assert "v1.2.0" in stored.external_id


def test_t06_source_settings_change_the_requests(db):
    _only(db, {"huggingface"})
    source = db.get(Source, "huggingface")
    source.policy_json = {"types": ["spaces"], "requests_per_poll_cap": 2}
    db.commit()
    spaces = [{"id": "acme/space-one", "sdk": "docker", "createdAt": "2026-11-02T00:00:00Z"}]
    transport = MapTransport({"https://huggingface.co/api/spaces": json.dumps(spaces).encode()})
    settings = make_settings()
    settings.source_mode = "live"
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert transport.calls == ["https://huggingface.co/api/spaces?limit=5"]
    assert db.query(SourceItem).filter_by(source_id="huggingface").count() == 1

    _only(db, {"hackernews"})
    hn = db.get(Source, "hackernews")
    hn.policy_json = {"collections": ["showstories"], "requests_per_poll_cap": 2}
    db.commit()
    show = MapTransport(
        {
            "https://hacker-news.firebaseio.com/v0/showstories.json": b"[11]",
            "https://hacker-news.firebaseio.com/v0/item/11.json": json.dumps(
                {"id": 11, "type": "story", "title": "Учебный Show HN материал", "url": "https://news.ycombinator.com/item?id=11", "time": 1762733400}
            ).encode(),
        }
    )
    collect_once(db, settings, transport=show, resolver=_resolver, now=NOW, force=True)
    assert show.calls[0].endswith("/showstories.json")
    assert not any("topstories" in url for url in show.calls)

    _only(db, {"pypi_updates"})
    pypi = db.get(Source, "pypi_updates")
    pypi.policy_json = {"feeds": ["https://pypi.org/rss/updates.xml"], "watched_projects": [], "requests_per_poll_cap": 1}
    db.commit()
    noisy = MapTransport({})
    collect_once(db, settings, transport=noisy, resolver=_resolver, now=NOW, force=True)
    assert noisy.calls == []
    assert db.get(Source, "pypi_updates").health == "not_configured"


def test_empty_release_list_is_not_configured(db):
    _only(db, {"github_releases"})
    db.get(Source, "github_releases").policy_json = {"watched_repos": [], "requests_per_poll_cap": 4}
    db.commit()
    transport = MapTransport({})
    settings = make_settings()
    settings.source_mode = "live"
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert transport.calls == []
    assert db.get(Source, "github_releases").health == "not_configured"


def test_transport_error_and_private_address_do_not_look_successful(db, monkeypatch):
    _only(db, {"cisa_kev"})
    settings = make_settings()
    settings.source_mode = "live"

    class Broken:
        def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
            del method, url, headers
            raise TransportError("timeout")

    report = collect_once(db, settings, transport=Broken(), resolver=_resolver, now=NOW, force=True)
    assert report.errors == 1
    assert db.get(Source, "cisa_kev").health == "error"

    connected: list[str] = []

    def _connect(address, timeout):
        del timeout
        connected.append(address[0])
        raise TimeoutError("should not connect")

    monkeypatch.setattr(socket, "create_connection", _connect)
    transport = PinnedHTTPTransport(resolver=lambda _host: ["10.1.1.1"], timeout=1)
    try:
        transport.request("GET", "https://www.cisa.gov/kev.json", {})
        raised = False
    except TransportError as exc:
        raised = exc.reason == "forbidden_ip"
    assert raised
    assert connected == []


def test_t07_ingest_calls_local_model_and_stays_in_review(db):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            seen["body"] = json.loads(self.rfile.read(length).decode())
            draft = draft_post(item(source_external_id="github:4242"), "github").draft
            draft["title"] = "Локальная модель из штатного разбора"
            payload = json.dumps({"message": {"role": "assistant", "content": json.dumps(draft)}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            del fmt, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = LocalLLMClient(f"http://127.0.0.1:{server.server_address[1]}/api/chat", model="local-test", timeout=3)
        result = ingest_source_item(db, item(source_external_id="github:4242"), render=False, llm_mode="local", llm_client=client)
        post = db.get(Post, result.post_id)
        assert post.title == "Локальная модель из штатного разбора"
        assert post.requires_review is True
        assert db.query(PublishingOutbox).count() == 0
        audit = db.query(AuditEvent).filter_by(action="llm_draft").one()
        assert audit.result == "draft"
        assert audit.payload_redacted["model"] == "local-test"
        assert "source_data" in seen["body"]["messages"][1]["content"]
    finally:
        server.shutdown()


def test_t08_llm_failure_falls_back_without_publishing(db, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("mock ingest opened a socket")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    mocked = ingest_source_item(db, item(source_external_id="github:5151"), render=False, llm_mode="mock")
    assert mocked.post_id
    monkeypatch.undo()
    client = LocalLLMClient("http://127.0.0.1:9/api/chat", model="local-test", timeout=0.2)
    failed = ingest_source_item(
        db,
        item(
            source_external_id="github:5152",
            source_url="https://github.com/acme/timeout",
            canonical_url="https://github.com/acme/timeout",
            repo_id="5152",
            title="Таймаут локальной модели в штатном разборе",
        ),
        render=False,
        llm_mode="local",
        llm_client=client,
    )
    post = db.get(Post, failed.post_id)
    assert post.requires_review is True
    assert db.query(PublishingOutbox).count() == 0
    assert db.query(AuditEvent).filter_by(action="llm_draft", result="fallback").count() == 1


def test_t09_collector_card_is_the_file_dispatch_sends(db):
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:cards"], "requests_per_poll_cap": 1}
    db.commit()
    transport = MapTransport({"https://api.github.com/search/": _github_body()})
    settings = make_settings()
    settings.source_mode = "live"
    settings.media_dir = MEDIA
    report = collect_cycle(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert report.ingested >= 1
    post = db.query(Post).order_by(Post.id.desc()).first()
    asset = db.query(MediaAsset).filter_by(post_id=post.id, status="ready").one()
    path = MEDIA / asset.file_path
    assert path.read_bytes().startswith(b"\xff\xd8\xff")
    assert asset.sha256
    from app.publishing.photo import load_card

    photo, digest = load_card(db, post, MEDIA)
    assert digest == asset.sha256
    from app.services.moderation import approve_post
    from tests.support import seed_users

    _owner, editor_user, _security = seed_users(db)
    approve_post(db, post, editor_user, confirmed=True)
    outbox = schedule_post(db, post, editor_user, due=NOW, confirmed=True, now=NOW)
    sender = ScriptedTransport([TgResult(200, message_id="1")])
    sent = dispatch_outbox(db, outbox, sender, now=NOW, media_dir=MEDIA)
    assert sent["state"] == "published"
    assert sender.calls[0]["photo"] == photo


def test_t10_and_backup_keep_the_same_jpeg_hash(db, tmp_path: Path):
    post, _owner, editor_user = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    db.add(refresh_card(post, channel, MEDIA))
    db.commit()
    asset = db.query(MediaAsset).filter_by(post_id=post.id).one()
    original = (MEDIA / asset.file_path).read_bytes()
    again = (MEDIA / asset.file_path).read_bytes()
    assert again == original
    backup = create_media_backup(MEDIA, tmp_path / "media.bin", "test-passphrase")
    restored = tmp_path / "restored"
    restore_media_backup(tmp_path / "media.bin", restored, "test-passphrase", backup["sha256"])
    assert (restored / asset.file_path).read_bytes() == original


def test_t11_and_t12_sandbox_chat_gate(db):
    post, _owner, editor_user = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    db.add(refresh_card(post, channel, MEDIA))
    channel.chat_id = "999"
    db.commit()
    outbox = schedule_post(db, post, editor_user, due=NOW, confirmed=True, now=NOW)
    foreign = ScriptedTransport([TgResult(200, message_id="1")])
    refused = dispatch_outbox(db, outbox, foreign, now=NOW, media_dir=MEDIA, allowed_chat_id="-100")
    assert refused["reason"] == "foreign_chat"
    assert foreign.calls == []
    spy = SpyTransport()
    gate = RestrictedChatTransport(spy, "-100")
    try:
        gate.send_photo({"chat_id": "999", "photo": b"\xff\xd8\xff", "caption": "нет"})
    except Exception:
        pass
    assert spy.calls == []
    outbox.state = "scheduled"
    channel.chat_id = "-100"
    db.commit()
    allowed = ScriptedTransport([TgResult(200, message_id="2")])
    sent = dispatch_outbox(db, outbox, allowed, now=NOW, media_dir=MEDIA, allowed_chat_id="-100")
    assert sent["state"] == "published"
    assert len(allowed.calls) == 1
    assert allowed.calls[0]["photo"].startswith(b"\xff\xd8\xff")


def test_t15_timeout_needs_reconciliation_and_does_not_retry(db):
    from app.publishing.telegram import AmbiguousTimeout

    post, _owner, editor_user = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    db.add(refresh_card(post, channel, MEDIA))
    db.commit()
    outbox = schedule_post(db, post, editor_user, due=NOW, confirmed=True, now=NOW)
    transport = ScriptedTransport([AmbiguousTimeout("timeout after request")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    assert result["state"] == "needs_reconciliation"
    again = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    assert again["calls"] == 0
    assert len(transport.calls) == 1


def test_t16_shipped_dev_cannot_publish():
    import yaml
    from app.publishing.gate import build_telegram_transport

    settings = make_settings()
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert build_telegram_transport(settings) is None
    document = yaml.safe_load(Path("compose.dev.yaml").read_text(encoding="utf-8"))
    for name in ("api", "collector", "scheduler", "migrate"):
        env = document["services"][name]["environment"]
        assert env["DRY_RUN"] == "true"
        assert env["PUBLISH_ENABLED"] == "false"
        assert env["GLOBAL_KILL_SWITCH"] == "true"
        assert env["SPONSORED_ENABLED"] == "false"
        assert env["SOURCE_MODE"] == "offline"


def test_t14_migration_lock_is_idempotent():
    import subprocess

    subprocess.run(["sudo", "-u", "postgres", "psql", "-c", "DROP DATABASE IF EXISTS tmn_rework_mig"], check=True)
    subprocess.run(["sudo", "-u", "postgres", "psql", "-c", "CREATE DATABASE tmn_rework_mig OWNER tmn"], check=True)
    url = "postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_rework_mig"
    engine = make_engine(url)
    prepare_database(engine, "migrate")
    prepare_database(engine, "migrate")
    assert assert_schema_head(engine) == SCHEMA_HEAD
    from sqlalchemy import text

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM alembic_version")).scalar()
    assert count == 1


def test_t17_ten_sources_have_explicit_states(db):
    settings = make_settings()
    settings.source_mode = "live"
    transport = MapTransport({})
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    rows = db.query(Source).order_by(Source.id).all()
    assert len(rows) == 10
    allowed = {"offline", "ok", "partial", "error", "not_configured", "blocked", "auth_error", "rate_limited", "unknown"}
    for source in rows:
        if not source.enabled:
            assert source.id == "cloudflare_changelog"
            continue
        assert source.health in allowed
    assert db.get(Source, "github_releases").health == "not_configured"
    assert db.get(Source, "pypi_updates").health == "not_configured"
    assert db.query(Channel).count() == 8
