"""R6 regressions. Every request stays inside the fake transport."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.adapters.http_client import HttpResult, safe_get
from app.core.models import Source, SourceEndpointState, SourceItem, Story
from app.pipeline.llm import LocalLLMClient, compose_draft
from app.publishing.gate import build_telegram_transport
from app.services.accounts import create_user
from app.workers.collect import _fetch_all, collect_once
from tests.conftest import make_settings
from tests.factories import NOW, item

CANARY = "CANARY-READ-TOKEN"
HF_CANARY = "CANARY-HF-TOKEN"


class RecordingTransport:
    def __init__(self, responder) -> None:
        self.responder = responder
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
        del method
        self.calls.append((url, dict(headers)))
        return self.responder(url, headers)


def _resolver(_host: str) -> list[str]:
    return ["8.8.8.8"]


def _only(db, ids: set[str]) -> None:
    for source in db.query(Source).all():
        source.enabled = source.id in ids
        source.last_run_at = None
        source.circuit_open = False
        source.consecutive_failures = 0
    db.commit()


def _live():
    settings = make_settings()
    settings.source_mode = "live"
    return settings


def _github_item(name: str) -> bytes:
    return json.dumps(
        {
            "items": [
                {
                    "id": abs(hash(name)) % 100000 + 1000,
                    "full_name": name,
                    "html_url": f"https://github.com/{name}",
                    "description": "Учебный репозиторий для проверки редиректов и условных запросов.",
                    "fork": False,
                    "archived": False,
                    "created_at": "2026-11-01T00:00:00Z",
                    "pushed_at": "2026-11-09T00:00:00Z",
                    "license": {"spdx_id": "Apache-2.0"},
                    "topics": [],
                }
            ]
        }
    ).encode()


def test_r6_t01_cross_origin_redirect_drops_the_token(db, caplog):
    caplog.set_level(logging.DEBUG)
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:one"], "requests_per_poll_cap": 2}
    db.commit()
    settings = _live()
    settings.github_read_token = CANARY

    def respond(url, headers):
        del headers
        if url.startswith("https://api.github.com/"):
            return HttpResult(302, {"Location": "https://huggingface.co/redirect-test"}, b"", url)
        return HttpResult(200, {}, b"should-not-run", url)

    transport = RecordingTransport(respond)
    report = collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    assert report.requests == 1
    assert len(transport.calls) == 1
    assert transport.calls[0][0].startswith("https://api.github.com/")
    assert transport.calls[0][1]["Authorization"] == f"Bearer {CANARY}"
    assert db.get(Source, "github_search").health == "error"
    assert CANARY not in db.get(Source, "github_search").last_error
    assert CANARY not in caplog.text

    same = RecordingTransport(
        lambda url, headers: HttpResult(
            200 if "other" in url else 302,
            {} if "other" in url else {"Location": "https://api.github.com/search/repositories?q=other"},
            _github_item("acme/same") if "other" in url else b"",
            url,
        )
    )
    outcome = safe_get(
        "https://api.github.com/search/repositories?q=topic%3Aone",
        same,
        _resolver,
        headers={"Authorization": f"Bearer {CANARY}", "Accept": "application/json"},
    )
    assert outcome.status == 200
    assert len(same.calls) == 2
    assert all(call[1].get("Authorization") == f"Bearer {CANARY}" for call in same.calls)
    assert all("api.github.com" in call[0] for call in same.calls)

    private = RecordingTransport(lambda url, headers: HttpResult(302, {"Location": "https://10.1.1.1/secret"}, b"", url))
    blocked = safe_get("https://api.github.com/search/repositories?q=one", private, _resolver, headers={"Authorization": f"Bearer {CANARY}"})
    assert len(private.calls) == 1
    assert blocked.ok is False
    assert CANARY not in blocked.reason

    plain = RecordingTransport(lambda url, headers: HttpResult(302, {"Location": "http://api.github.com/search/repositories?q=one"}, b"", url))
    downgraded = safe_get("https://api.github.com/search/repositories?q=one", plain, _resolver)
    assert len(plain.calls) == 1
    assert downgraded.reason in {"scheme", "redirect_cross_origin"}

    loop = {"https://api.github.com/a": "https://api.github.com/b", "https://api.github.com/b": "https://api.github.com/a"}
    looper = RecordingTransport(lambda url, headers: HttpResult(302, {"Location": loop.get(url, "https://api.github.com/a")}, b"", url))
    cycled = safe_get("https://api.github.com/a", looper, _resolver)
    assert cycled.reason == "redirect_loop"
    assert len(looper.calls) <= 3

    chain = {f"https://api.github.com/r{i}": f"https://api.github.com/r{i+1}" for i in range(6)}
    hopper = RecordingTransport(lambda url, headers: HttpResult(302, {"Location": chain.get(url, "https://api.github.com/r0")}, b"", url))
    too_many = safe_get("https://api.github.com/r0", hopper, _resolver)
    assert too_many.reason == "too_many_redirects"
    assert len(hopper.calls) == 4


def test_r6_t02_304_does_not_cancel_the_other_url(db):
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:one", "topic:two"], "requests_per_poll_cap": 2, "query_cursor": 0}
    db.commit()
    settings = _live()
    bodies = {
        "topic%3Aone": _github_item("acme/from-one"),
        "topic%3Atwo": _github_item("acme/from-two"),
    }

    def run(order):
        state = {"left": order[0], "right": order[1]}

        def respond(url, headers):
            del headers
            which = "topic%3Aone" if "topic%3Aone" in url else "topic%3Atwo"
            status = state["left"] if "topic%3Aone" in url else state["right"]
            if status == 304:
                return HttpResult(304, {}, b"", url)
            return HttpResult(200, {"ETag": which}, bodies[which], url)

        transport = RecordingTransport(respond)
        report = collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
        return transport, report

    first, report = run((304, 200))
    assert len(first.calls) == 2
    assert report.ingested >= 1
    assert db.query(Story).filter(Story.canonical_url.contains("from-two")).count() == 1
    second, _again = run((200, 304))
    assert len(second.calls) == 2
    assert db.query(Story).filter(Story.canonical_url.contains("from-one")).count() == 1


def test_r6_t03_etags_stay_on_their_own_url(db):
    _only(db, {"github_search"})
    source = db.get(Source, "github_search")
    source.policy_json = {"queries": ["topic:one", "topic:two"], "requests_per_poll_cap": 2}
    db.commit()
    settings = _live()

    def respond(url, headers):
        tag = "W/one" if "topic%3Aone" in url else "W/two"
        if headers.get("If-None-Match") == tag:
            return HttpResult(304, {"ETag": tag}, b"", url)
        return HttpResult(200, {"ETag": tag}, _github_item("acme/" + ("one" if tag == "W/one" else "two")), url)

    transport = RecordingTransport(respond)
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    db.expire_all()
    rows = db.query(SourceEndpointState).all()
    assert {row.etag for row in rows} == {"W/one", "W/two"}
    transport.calls.clear()
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    sent = {call[0]: call[1].get("If-None-Match") for call in transport.calls}
    assert any(url for url, tag in sent.items() if "topic%3Aone" in url and tag == "W/one")
    assert any(url for url, tag in sent.items() if "topic%3Atwo" in url and tag == "W/two")
    assert all(tag in {"W/one", "W/two"} for tag in sent.values())


def test_r6_t04_hackernews_budget_ignores_earlier_sources(db):
    _only(db, {"hackernews"})
    source = db.get(Source, "hackernews")
    source.policy_json = {"collections": ["topstories"], "requests_per_poll_cap": 4}
    db.commit()
    story = {"id": 11, "type": "story", "title": "Учебный HN материал", "url": "https://news.ycombinator.com/item?id=11", "time": 1793577600}

    def respond(url, headers):
        del headers
        if url.endswith("/topstories.json"):
            return HttpResult(200, {}, json.dumps([11, 12, 13]).encode(), url)
        return HttpResult(200, {}, json.dumps({**story, "id": int(url.split("/item/")[1].split(".")[0])}).encode(), url)

    def once(prior: int):
        transport = RecordingTransport(respond)
        report_items = []
        from app.workers.collect import CollectReport

        report = CollectReport(requests=prior)
        _fetch_all(db, source, ["https://hacker-news.firebaseio.com/v0/topstories.json"], transport, _resolver, _live(), report, NOW)
        report_items.append(report.requests - prior)
        return len(transport.calls), report.requests - prior

    baseline = once(0)
    assert baseline[0] == 4
    assert once(5) == baseline
    assert once(100) == baseline


def test_r6_t05_three_hackernews_collections_share_one_cap(db):
    _only(db, {"hackernews"})
    source = db.get(Source, "hackernews")
    source.policy_json = {"collections": ["topstories", "newstories", "showstories"], "requests_per_poll_cap": 8}
    db.commit()
    lists = {"topstories": [1, 2, 3, 4], "newstories": [3, 6, 7], "showstories": [1, 8, 9]}

    def respond(url, headers):
        del headers
        for name, ids in lists.items():
            if url.endswith(f"/{name}.json"):
                return HttpResult(200, {}, json.dumps(ids).encode(), url)
        story_id = int(url.split("/item/")[1].split(".")[0])
        body = {"id": story_id, "type": "story", "title": f"Учебный материал {story_id}", "url": f"https://news.ycombinator.com/item?id={story_id}", "time": 1793577600}
        return HttpResult(200, {}, json.dumps(body).encode(), url)

    transport = RecordingTransport(respond)
    report = collect_once(db, _live(), transport=transport, resolver=_resolver, now=NOW, force=True)
    assert len(transport.calls) <= 8
    assert report.requests <= 8
    ids = [row.external_id for row in db.query(SourceItem).filter_by(source_id="hackernews")]
    assert len(ids) == len(set(ids))
    assert db.get(Source, "hackernews").health == "partial"


def test_r6_t06_release_metadata_stays_with_its_repository(db):
    _only(db, {"github_releases"})
    source = db.get(Source, "github_releases")
    source.policy_json = {"watched_repos": ["acme/one", "acme/two", "acme/three"], "requests_per_poll_cap": 5}
    db.commit()
    docs = {
        "acme/one": {"id": 1, "full_name": "acme/one", "html_url": "https://github.com/acme/one", "license": {"spdx_id": "Apache-2.0"}},
        "acme/two": {"id": 2, "full_name": "acme/two", "html_url": "https://github.com/acme/two", "license": {"spdx_id": "MIT"}},
    }

    def release(name, tag):
        return [{"tag_name": tag, "html_url": f"https://github.com/{name}/releases/tag/{tag}", "published_at": "2026-11-02T00:00:00Z", "body": "Учебный релиз."}]

    def respond(url, headers):
        del headers
        if url.endswith("/releases?per_page=3"):
            name = url.split("/repos/")[1].split("/releases")[0]
            tag = "v1" if name.endswith("one") else "v2"
            return HttpResult(200, {}, json.dumps(release(name, tag)).encode(), url)
        if url.endswith("/acme/one"):
            return HttpResult(500, {}, b"", url)
        name = url.split("/repos/")[1]
        return HttpResult(200, {}, json.dumps(docs[name]).encode(), url)

    transport = RecordingTransport(respond)
    collect_once(db, _live(), transport=transport, resolver=_resolver, now=NOW, force=True)
    requested = [call[0] for call in transport.calls]
    assert not any("acme/three" in url for url in requested)
    assert len(requested) == 4
    one = db.query(Story).filter(Story.title.contains("acme/one")).one()
    two = db.query(Story).filter(Story.title.contains("acme/two")).one()
    assert one.license_spdx in {"", None}
    assert two.license_spdx == "MIT"
    assert "v1" in one.title and "v2" in two.title


def test_r6_t07_local_model_refuses_other_hosts(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("disallowed model endpoint opened a socket")

    monkeypatch.setattr("urllib.request.build_opener", explode)
    external = LocalLLMClient("https://example.com", api_path="/api/chat")
    drafted = compose_draft(item(source_external_id="github:r6"), "github", mode="local", client=external)
    assert "llm_fallback" in drafted.warnings
    monkeypatch.undo()

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if self.path == "/api/chat":
                payload = json.dumps({"message": {"content": json.dumps(item_draft())}}).encode()
                self.send_response(200)
            else:
                payload = b""
                self.send_response(302)
                self.send_header("Location", "https://example.com/api/chat")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            del fmt, args

    def item_draft():
        from app.pipeline.editor import draft_post

        draft = draft_post(item(source_external_id="github:r6b"), "github").draft
        draft["title"] = "Локальный корень дополнен путём чата"
        return draft

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = LocalLLMClient(f"http://127.0.0.1:{server.server_address[1]}", model="local-test", timeout=3)
        accepted = compose_draft(item(source_external_id="github:r6b", repo_id="r6b"), "github", mode="local", client=root)
        assert seen["path"] == "/api/chat"
        assert accepted.draft["title"] == "Локальный корень дополнен путём чата"
        seen.clear()
        redirecting = LocalLLMClient(f"http://127.0.0.1:{server.server_address[1]}/api/generate", model="local-test", timeout=3)
        # The test server answers 302 for every path except /api/chat.
        fallen = compose_draft(item(source_external_id="github:r6c", repo_id="r6c", source_url="https://github.com/acme/r6c", canonical_url="https://github.com/acme/r6c"), "github", mode="local", client=redirecting)
        assert "llm_fallback" in fallen.warnings
    finally:
        server.shutdown()


def test_r6_t08_hf_token_stays_on_huggingface(db):
    _only(db, {"huggingface", "github_search"})
    db.get(Source, "github_search").policy_json = {"queries": ["topic:one"], "requests_per_poll_cap": 1}
    db.get(Source, "huggingface").policy_json = {"types": ["models"], "requests_per_poll_cap": 1}
    db.commit()
    settings = _live()
    settings.github_read_token = CANARY
    settings.hf_read_token = HF_CANARY

    def respond(url, headers):
        del headers
        if "huggingface.co" in url:
            return HttpResult(200, {}, b"[]", url)
        return HttpResult(200, {}, _github_item("acme/token"), url)

    transport = RecordingTransport(respond)
    collect_once(db, settings, transport=transport, resolver=_resolver, now=NOW, force=True)
    for url, headers in transport.calls:
        if "huggingface.co" in url:
            assert headers.get("Authorization") == f"Bearer {HF_CANARY}"
            assert CANARY not in headers.get("Authorization", "")
        if "api.github.com" in url:
            assert headers.get("Authorization") == f"Bearer {CANARY}"
            assert HF_CANARY not in "".join(headers.values())

    hopped = RecordingTransport(lambda url, headers: HttpResult(302, {"Location": "https://api.github.com/repos/acme/widget"}, b"", url))
    safe_get(
        "https://huggingface.co/api/models?limit=1",
        hopped,
        _resolver,
        headers={"Authorization": f"Bearer {HF_CANARY}"},
    )
    assert len(hopped.calls) == 1
    assert HF_CANARY not in hopped.calls[0][0]


def test_r6_t09_ready_does_not_claim_a_dead_collector(db, client):
    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    create_user(db, username="editor", password="editor-password-1", role="EDITOR")
    db.commit()
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["scope"] == "database"
    assert ready.json()["status"] == "ready"
    assert "everything" not in ready.text
    assert client.get("/health/components").status_code == 401
    client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
    assert client.get("/health/components").status_code == 403
    client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    body = client.get("/health/components").json()
    assert body["status"] == "degraded"
    assert body["components"]["collector"]["status"] == "missing"
    assert "postgresql" not in json.dumps(body)
    assert "redis://" not in json.dumps(body)


def test_r6_t14_shipped_flags_still_block_telegram():
    settings = make_settings()
    assert build_telegram_transport(settings) is None
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert settings.sponsored_enabled is False
    assert settings.source_mode == "offline"
