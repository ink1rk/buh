from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pyotp
import yaml
from app.adapters.http_client import HttpResult, safe_get
from app.core.models import AdCampaign, AuditEvent, Post, PublishingOutbox, RuntimeSetting, User
from app.core.models import Session as SessionRow
from app.core.redact import redact
from app.core.security import token_hash
from app.core.timeutil import utcnow
from app.pipeline.editor import draft_post
from app.pipeline.rank import LICENSE_CLAIM_RE
from app.pipeline.urlsec import assert_url_safe
from app.services.accounts import AuthError
from app.services.moderation import approve_post
from tests.conftest import make_settings
from tests.factories import fact, item
from tests.support import ROOT, approved_post, ingest, seed_users

ROOT_DIR = Path(__file__).resolve().parents[1]


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(self, method: str, url: str, headers: dict[str, str]) -> HttpResult:
        del method, headers
        self.calls.append(url)
        if len(self.calls) == 1:
            return HttpResult(302, {"Location": "http://127.0.0.1:8006/secret"}, url=url)
        return HttpResult(200, {}, b"secret", url=url)


def _resolver(host: str) -> list[str]:
    del host
    return ["8.8.8.8"]


def test_e01_ssrf_blocked_before_request():
    transport = RecordingTransport()
    for url in ("http://127.0.0.1/", "https://[fc00::1]/", "https://169.254.169.254/latest/meta-data/"):
        outcome = safe_get(url, transport, _resolver)
        assert outcome.ok is False
        assert outcome.requests == 0
    assert transport.calls == []
    try:
        assert_url_safe("http://127.0.0.1/", _resolver)
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_e02_redirect_to_private_is_not_followed():
    transport = RecordingTransport()
    outcome = safe_get("https://allowlisted.example/start", transport, _resolver)
    assert outcome.ok is False
    assert outcome.reason == "scheme"
    assert transport.calls == ["https://allowlisted.example/start"]


def test_e03_token_is_redacted(db):
    token = "ghp_" + "a" * 24
    source = item(
        title=f"Widget note {token}",
        untrusted_text=f"readme contains {token}",
        facts=[
            fact("f1", f"Описание содержит {token} и его нельзя переносить.", "https://github.com/acme/widget", token),
            fact("f2", "Репозиторий описывает локальный запуск служебных задач.", "https://github.com/acme/widget", "local tasks"),
        ],
    )
    result = ingest(db, source)
    assert token not in (result.public_text or "")
    from app.core.models import SourceItem

    stored = db.query(SourceItem).one()
    assert token not in json.dumps(stored.raw_json)
    assert "[REDACTED_GITHUB]" in redact(f"leaked {token}")


def test_e04_compose_has_no_public_data_ports():
    document = yaml.safe_load((ROOT_DIR / "compose.dev.yaml").read_text(encoding="utf-8"))
    for name in ("db", "redis", "scheduler", "collector"):
        assert "ports" not in document["services"][name]
    assert document["services"]["api"]["ports"] == ["127.0.0.1:8787:8787"]
    assert document["services"]["api"]["user"] == "1000:1000"
    assert document["services"]["api"].get("privileged") is not True
    rendered = (ROOT_DIR / "compose.dev.yaml").read_text(encoding="utf-8")
    assert "docker.sock" not in rendered


def test_e05_sponsor_without_legal_approval_is_blocked(db):
    post, owner, editor = approved_post(db)
    campaign = AdCampaign(advertiser="Example", channel_id=post.channel_id, marked=False, legal_status="pending")
    db.add(campaign)
    db.flush()
    post.flags_json = ["sponsored"]
    post.sponsored_campaign_id = campaign.id
    post.review_status = "NEEDS_REVIEW"
    post.approver_ids_json = []
    db.commit()
    for actor in (editor, owner):
        try:
            approve_post(db, post, actor, confirmed=True)
            blocked = False
        except AuthError as exc:
            blocked = exc.status == 403
        assert blocked is True
    assert db.query(PublishingOutbox).count() == 0


def test_e06_unknown_license_cannot_claim_oss(db):
    source = item(license_state="unknown", license_spdx=None, topics=[])
    drafted = draft_post(source, "github")
    assert drafted.blocked is False
    assert not LICENSE_CLAIM_RE.search(drafted.public_text)
    assert "#opensource" not in drafted.draft["suggested_hashtags"]
    result = ingest(db, source)
    _owner, editor, _security = seed_users(db)
    post = db.get(Post, result.post_id)
    post.body = "Проект распространяется под лицензией MIT и его можно назвать open-source."
    db.commit()
    try:
        approve_post(db, post, editor, confirmed=True)
        blocked = False
    except AuthError as exc:
        blocked = exc.status == 422
    assert blocked is True


def test_e07_mfa_session_and_rate_limit(client, engine):
    from app.core.db import make_session_factory
    from app.core.security import new_totp_secret
    from app.services.accounts import create_user
    from app.services.bootstrap import bootstrap

    factory = make_session_factory(engine)
    secret = new_totp_secret()
    with factory() as session:
        bootstrap(session, make_settings())
        create_user(session, username="owner", password="owner-password-12", role="OWNER", mfa_secret=secret, mfa_enabled=True)
        create_user(session, username="plain", password="plain-password-1", role="VIEWER")
        session.commit()
    wrong = "000000"
    if pyotp.TOTP(secret).now() == wrong:
        wrong = "111111"
    ok = client.post("/api/v1/auth/login", json={"username": "plain", "password": "plain-password-1"})
    assert ok.status_code == 200
    raw = client.cookies.get("tmn_session")
    with factory() as session:
        row = session.get(SessionRow, token_hash(raw))
        row.expires_at = utcnow() - timedelta(minutes=1)
        session.commit()
    expired = client.get("/api/v1/auth/me")
    assert expired.status_code == 401
    started = client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    assert started.status_code == 200
    assert started.json()["mfa_required"] is True
    denied = client.post("/api/v1/auth/mfa", json={"mfa_token": started.json()["mfa_token"], "code": wrong})
    assert denied.status_code == 401
    for _ in range(5):
        failed = client.post("/api/v1/auth/login", json={"username": "plain", "password": "wrong-password"})
        assert failed.status_code == 401
    limited = client.post("/api/v1/auth/login", json={"username": "plain", "password": "wrong-password"})
    assert limited.status_code == 429
    with factory() as session:
        assert session.query(AuditEvent).filter_by(action="mfa", result="denied").count() == 1
        assert session.query(AuditEvent).filter_by(action="session", result="expired").count() == 1


def test_e08_bandit_has_no_high_findings():
    completed = subprocess.run(
        [sys.executable, "-m", "bandit", "-c", "pyproject.toml", "-r", "app", "-f", "json", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout or "{}")
    highs = [row for row in payload.get("results", []) if row.get("issue_severity") == "HIGH"]
    assert highs == []


def test_editor_cannot_flip_kill_switch(client, engine):
    from app.core.db import make_session_factory
    from app.services.accounts import create_user
    from app.services.bootstrap import bootstrap

    factory = make_session_factory(engine)
    with factory() as session:
        bootstrap(session, make_settings())
        create_user(session, username="editor", password="editor-password-1", role="EDITOR")
        session.commit()
    login = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
    csrf = login.json()["csrf_token"]
    response = client.post(
        "/api/v1/system/settings",
        json={"global_kill_switch": False, "confirm": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    with factory() as session:
        assert session.get(RuntimeSetting, "global_kill_switch").value_json["value"] is True
        assert session.get(User, 1).role == "EDITOR"
