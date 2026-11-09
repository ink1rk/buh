from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml
from app.adapters.registry import ADAPTER_TYPES
from app.core.config import ROOT, assert_can_boot
from app.core.models import Channel, Post, User
from app.publishing.leader import LeaderLock
from app.services.accounts import create_user
from app.services.bootstrap import load_channels_document, shipped_is_safe
from app.services.dispatch import scheduler_tick
from sqlalchemy import inspect
from tests.conftest import make_settings
from tests.factories import NOW, item

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_a02_eight_channels():
    document = load_channels_document(ROOT / "configs" / "channels.yaml")
    shipped_is_safe(document)
    ids = [channel["id"] for channel in document["channels"]]
    assert ids == ["ai_news", "ai_tools", "github", "cyber", "infra", "homelab", "dev", "future"]
    assert document["network"]["timezone"] == "Europe/Moscow"


def test_a02_database_seed(db):
    rows = db.query(Channel).order_by(Channel.id).all()
    assert len(rows) == 8
    assert all(row.publish_enabled is False for row in rows)
    assert all(row.timezone == "Europe/Moscow" for row in rows)
    assert len(ADAPTER_TYPES) >= 7


def test_a03_alembic_upgrade():
    name = "tmn_alembic"
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"])
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"CREATE DATABASE {name} OWNER tmn"])
    url = f"postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/{name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT_DIR, env=env)
    from sqlalchemy import create_engine

    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    assert {"stories", "posts", "publishing_outbox", "audit_events", "channels"} <= names
    indexes = {index["name"] for index in inspect(engine).get_indexes("publishing_outbox")}
    assert "uq_outbox_one_active" in indexes
    engine.dispose()


def test_a04_anonymous_cannot_approve(client, engine):
    from app.core.db import make_session_factory
    from app.services.editorial import ingest_source_item

    factory = make_session_factory(engine)
    with factory() as session:
        from app.services.bootstrap import bootstrap

        bootstrap(session, make_settings())
        session.commit()
        result = ingest_source_item(session, item(), media_dir=ROOT_DIR / "var" / "media")
        post_id = result.post_id
        before = session.get(Post, post_id).review_status
    response = client.post(f"/api/v1/posts/{post_id}/approve", json={"confirm": True, "reason": "no"})
    assert response.status_code == 401
    with factory() as session:
        assert session.get(Post, post_id).review_status == before
        assert session.query(__import__("app.core.models", fromlist=["AuditEvent"]).AuditEvent).count() >= 1


def test_a05_editor_cannot_escalate(client, engine):
    from app.core.db import make_session_factory

    factory = make_session_factory(engine)
    with factory() as session:
        from app.services.bootstrap import bootstrap

        bootstrap(session, make_settings())
        editor = create_user(session, username="editor", password="editor-password-1", role="EDITOR")
        session.commit()
        editor_id = editor.id
    login = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    settings = client.post(
        "/api/v1/system/settings",
        json={"publish_enabled": True, "confirm": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert settings.status_code == 403
    role = client.post(
        f"/api/v1/users/{editor_id}/role",
        json={"role": "OWNER", "confirm": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert role.status_code == 403
    with factory() as session:
        assert session.get(User, editor_id).role == "EDITOR"


def test_a06_single_scheduler_leader(engine, db):
    from app.core.security import Policy
    from app.services.accounts import create_user
    from app.services.editorial import ingest_source_item
    from app.services.moderation import approve_post

    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    editor = create_user(db, username="ed", password="editor-password-1", role="EDITOR")
    db.commit()
    created = ingest_source_item(db, item(topics=["devtools"]), media_dir=ROOT_DIR / "var" / "media")
    post = db.get(Post, created.post_id)
    approve_post(db, post, editor, confirmed=True)
    channel = db.get(__import__("app.core.models", fromlist=["Channel"]).Channel, post.channel_id)
    channel.schedule_json = ["09:10"]
    db.commit()
    first = LeaderLock(engine)
    second = LeaderLock(engine)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        policy = Policy(True, False, False, False)
        missed = scheduler_tick(db, leader=False, now=NOW, policy=policy)
        assert missed.scheduled == 0
        led = scheduler_tick(db, leader=True, now=NOW, policy=policy)
        again = scheduler_tick(db, leader=True, now=NOW, policy=policy)
        assert led.scheduled == 1
        assert again.scheduled == 0
        first.release()
        assert second.acquire() is True
        restarted = scheduler_tick(db, leader=True, now=NOW, policy=policy)
        assert restarted.scheduled == 0
    finally:
        second.close()
        first.close()


def test_production_boot_is_refused():
    settings = make_settings()
    settings.environment = "production"
    try:
        assert_can_boot(settings)
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True


def test_compose_file_has_no_database_host_ports():
    document = yaml.safe_load((ROOT_DIR / "compose.dev.yaml").read_text(encoding="utf-8"))
    assert "ports" not in document["services"]["db"]
    assert "ports" not in document["services"]["redis"]
    assert document["services"]["api"]["ports"] == ["127.0.0.1:8787:8787"]
    assert document["services"]["api"]["user"] == "1000:1000"
    assert document["services"]["db"].get("privileged") is not True
