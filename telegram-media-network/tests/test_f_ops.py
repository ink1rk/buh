from __future__ import annotations

import subprocess
import time
from datetime import timedelta
from pathlib import Path

import yaml
from app.core.db import init_schema, make_engine, make_session_factory
from app.core.models import Channel, Post, PublishingOutbox, Story, StoryAlias
from app.core.security import Policy
from app.core.timeutil import slot_to_utc
from app.media.renderer import render_card
from app.ops.backup import create_encrypted_backup, decrypt_bytes, restore_encrypted_backup
from app.ops.report import pilot_report
from app.publishing.schedule import DueItem, select_sendable
from app.publishing.telegram import ScriptedTransport, TgResult
from app.services.accounts import create_user
from app.services.bootstrap import bootstrap
from app.services.dispatch import scheduler_tick
from app.services.editorial import ingest_source_item
from app.services.moderation import approve_post, schedule_post
from sqlalchemy.exc import IntegrityError
from tests.conftest import make_settings
from tests.factories import NOW, fact, item, sha
from tests.support import MEDIA, approved_post, ingest

ROOT = Path(__file__).resolve().parents[1]


def _recreate(name: str) -> str:
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"])
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"CREATE DATABASE {name} OWNER tmn"])
    return f"postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/{name}"


def test_f01_f02_encrypted_backup_restores(tmp_path: Path):
    source_url = _recreate("tmn_backup_src")
    dest_url = _recreate("tmn_backup_dst")
    engine = make_engine(source_url)
    init_schema(engine)
    session = make_session_factory(engine)()
    settings = make_settings()
    settings.database_url = source_url
    bootstrap(session, settings)
    create_user(session, username="owner", password="owner-password-12", role="OWNER")
    ingest_source_item(session, item(source_external_id="backup-1"), render=False, media_dir=MEDIA)
    session.commit()
    stories = session.query(Story).count()
    posts = session.query(Post).count()
    alias = session.query(StoryAlias).first().alias
    session.close()
    engine.dispose()
    dest = tmp_path / "tmn.backup"
    saved = create_encrypted_backup(source_url, dest, "backup-passphrase")
    assert dest.stat().st_mode & 0o777 == 0o600
    assert decrypt_bytes(dest.read_bytes(), "backup-passphrase")
    sidecar = dest.with_suffix(dest.suffix + ".sha256").read_text(encoding="utf-8").strip()
    assert sidecar == saved["sha256"]
    restore_encrypted_backup(dest, dest_url, "backup-passphrase", saved["sha256"])
    restored = make_engine(dest_url)
    check = make_session_factory(restored)()
    assert check.query(Story).count() == stories
    assert check.query(Post).count() == posts
    story_id = check.query(Story).one().id
    check.add(StoryAlias(alias=alias, story_id=story_id))
    try:
        check.commit()
        duplicated = True
    except IntegrityError:
        check.rollback()
        duplicated = False
    assert duplicated is False
    check.close()
    restored.dispose()


def test_f03_kill_switch_sends_nothing(db):
    _post, _owner, editor = approved_post(db)
    del editor
    transport = ScriptedTransport([TgResult(200, message_id="1")])
    result = scheduler_tick(db, leader=True, now=NOW, policy=Policy(False, True, True, False), transport=transport)
    assert result.blocked == "kill_switch"
    assert result.sent == 0
    assert transport.calls == []
    assert db.query(PublishingOutbox).count() == 0


def test_f04_moscow_and_dst_conversion():
    moscow = slot_to_utc(NOW, "09:10", "Europe/Moscow")
    assert moscow.hour == 6 and moscow.minute == 10
    summer = slot_to_utc(NOW.replace(year=2026, month=7, day=1), "09:10", "America/New_York")
    winter = slot_to_utc(NOW.replace(year=2026, month=1, day=15), "09:10", "America/New_York")
    assert summer.hour == 13 and summer.minute == 10
    assert winter.hour == 14 and winter.minute == 10


def test_f05_stale_backlog_is_not_a_burst(db):
    post, _owner, editor = approved_post(db)
    fresh = schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    older = ingest(
        db,
        item(
            source_external_id="github:808",
            source_url="https://github.com/acme/older",
            repo_id="808",
            title="Older Acme tool for local tasks",
            published_at=NOW - timedelta(days=2),
            raw_sha256=sha("older"),
        ),
    )
    older_post = db.get(Post, older.post_id)
    approve_post(db, older_post, editor, confirmed=True)
    stale_row = schedule_post(db, older_post, editor, due=NOW - timedelta(days=2), confirmed=True, now=NOW)
    stale_story = db.get(Story, post.story_id)
    chosen = select_sendable(
        [
            DueItem(NOW - timedelta(days=2), stale_story.published_utc - timedelta(days=2), post.channel_id),
            DueItem(NOW, stale_story.published_utc, post.channel_id),
        ],
        NOW,
        fresh_hours=36,
        limit=1,
    )
    assert len(chosen) == 1
    assert chosen[0].due_utc == NOW
    transport = ScriptedTransport([TgResult(200, message_id="9")])
    channel = db.get(Channel, post.channel_id)
    channel.publish_enabled = True
    db.commit()
    tick = scheduler_tick(db, leader=True, now=NOW, policy=Policy(False, True, False, False), transport=transport)
    db.refresh(fresh)
    db.refresh(stale_row)
    assert tick.sent == 1
    assert fresh.state == "published"
    assert stale_row.state == "scheduled"
    assert len(transport.calls) == 1


def test_f06_views_are_not_invented(client, engine):
    from app.core.db import make_session_factory
    from app.services.bootstrap import bootstrap

    factory = make_session_factory(engine)
    with factory() as session:
        bootstrap(session, make_settings())
        create_user(session, username="viewer", password="viewer-password-1", role="VIEWER")
        session.commit()
    login = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-1"})
    assert login.status_code == 200
    payload = client.get("/api/v1/analytics").json()
    assert payload["views_available"] is False
    assert payload["channels"]
    assert all(row["views"] is None and row["views_label"] == "н/д" for row in payload["channels"])
    page = client.get("/analytics")
    assert page.status_code == 200
    assert "н/д" in page.text


def test_f07_thousand_items_and_fifty_posts(db):
    started = time.perf_counter()
    for index in range(1000):
        ingest_source_item(
            db,
            item(
                source_id="bulk",
                source_external_id=f"bulk:{index}",
                source_url=f"https://example.com/items/{index}",
                canonical_url=f"https://example.com/items/{index}",
                content_kind="news",
                repo_id=None,
                published_at=None,
                practical=False,
                is_new=False,
                audience=0.2,
                has_changelog=False,
                license_state="unknown",
                license_spdx=None,
                title=f"Undated note number {index:04d}",
                facts=[
                    fact(
                        "f1",
                        f"Короткая заметка номер {index} без даты и без практического сценария.",
                        f"https://example.com/items/{index}",
                        "note",
                    )
                ],
                raw_sha256=sha(f"bulk-{index}"),
            ),
            render=False,
            media_dir=MEDIA,
        )
    for index in range(50):
        result = ingest_source_item(
            db,
            item(
                source_external_id=f"github:{20000 + index}",
                source_url=f"https://github.com/acme/post-{index}",
                canonical_url=f"https://github.com/acme/post-{index}",
                repo_id=str(20000 + index),
                title=f"Acme post {index:02d} local task runner",
                audience=1.0,
                raw_sha256=sha(f"post-{index}"),
            ),
            render=True,
            media_dir=MEDIA,
        )
        assert result.post_id is not None
    elapsed = time.perf_counter() - started
    assert db.query(Story).count() >= 1050
    assert db.query(Post).count() == 50
    assert elapsed < 180
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "f07_timing.txt").write_text(f"elapsed_seconds={elapsed:.2f}\n", encoding="utf-8")


def test_f08_pilot_report_is_unsigned(db):
    ingest(db)
    report = pilot_report(db)
    assert report["stories"] >= 1
    assert report["sign_off"] is None
    assert report["sign_off_status"] == "BLOCKED"
    assert "человека" in report["reason"]


def test_card_previews_for_eight_brands():
    document = yaml.safe_load((ROOT / "configs" / "channels.yaml").read_text(encoding="utf-8"))
    out = ROOT / "reports" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    titles = {
        "news": "Коротко: что изменилось и чего источник не подтверждает",
        "tool": "Локальный инструмент для ежедневной служебной задачи",
        "security": "CVE-2026-1000: обновить продукт по рекомендации источника",
    }
    for channel in document["channels"]:
        theme = channel["theme"]
        for template, title in titles.items():
            rendered = render_card(
                channel_title=channel["title"],
                primary=theme["primary"],
                accent=theme["accent"],
                template=template,
                title=title,
                kicker=template.upper(),
                footer=channel["title"],
                cve="CVE-2026-1000" if template == "security" else "",
            )
            assert rendered.layout.fits is True
            (out / f"{channel['id']}-{template}.jpg").write_bytes(rendered.jpeg)


def test_a01_compose_file_renders():
    """Render the dev compose file. Readiness of the running stack is in reports/STAGE_6.md."""
    import os

    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_PASSWORD": "local-only",
            "REDIS_PASSWORD": "local-only",
            "SESSION_SECRET": "local-only-session-secret",
        }
    )
    docker = ["docker"]
    probe = subprocess.run([*docker, "info"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        probe = subprocess.run(["sudo", *docker, "info"], capture_output=True, text=True, check=False)
        docker = ["sudo", "docker"]
    if probe.returncode != 0:
        import pytest

        pytest.skip("NOT_RUN: dockerd is not available, so compose runtime was not executed")
    subprocess.check_call([*docker, "compose", "-f", "compose.dev.yaml", "config"], cwd=ROOT, env=env)
