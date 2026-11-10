"""Global product upgrade. Demo rows stay synthetic. Telegram is not contacted."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from app.core.db import make_engine
from app.core.models import (
    AdCampaign,
    Channel,
    ClusterMember,
    Episode,
    EvidenceSnapshot,
    FinanceEvent,
    Post,
    PublishedMessage,
    PublishingOutbox,
    RankedCandidate,
    RuntimeSetting,
    SourceItem,
    Story,
    StoryCluster,
)
from app.media.renderer import choose_rights, render_network_card, write_studio_pack
from app.product.demo_pack import SHARED_URL, build_pack
from app.product.drafts import fallback_from_invalid, materialise_desk, variants_for
from app.product.insights import funnel, seed_demo_campaigns
from app.product.programs import _quiet, move_episode, propose_fortnight
from app.product.radar import import_observations, rank_open_clusters
from app.publishing.gate import build_telegram_transport
from app.publishing.telegram import ScriptedTransport, TgResult
from app.services.accounts import create_user
from app.services.dispatch import dispatch_outbox
from app.services.editorial import refresh_card
from app.services.moderation import schedule_post
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from tests.conftest import make_settings
from tests.factories import NOW
from tests.support import MEDIA, approved_post

ROOT_DIR = Path(__file__).resolve().parents[1]


def _load(db):
    stats = import_observations(db, build_pack(), NOW)
    posts = materialise_desk(db)
    return stats, posts


def test_g1_pack_groups_scores_and_reimports(db):
    stats, _posts = _load(db)
    assert stats["created"] == 162
    assert stats["duplicates"] == 0
    per_channel = {}
    for row in build_pack():
        per_channel[row["channel_id"]] = per_channel.get(row["channel_id"], 0) + 1
    assert min(per_channel.values()) >= 20
    stories = db.query(Story).filter_by(canonical_url=SHARED_URL).all()
    assert len(stories) == 1
    cluster = db.query(StoryCluster).filter_by(cluster_key=stories[0].cluster_id).one()
    members = db.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").count()
    assert members == 3
    releases = db.query(Story).filter(Story.repo_identity == "acme/demo-runner").all()
    assert len(releases) == 2
    similar = db.query(ClusterMember).filter_by(relation="merge_candidate").count()
    assert similar >= 1
    assert db.query(Story).count() == 160
    ranked = db.query(RankedCandidate).all()
    assert ranked
    assert all(row.explanation and "relevance" in row.explanation for row in ranked)
    stars = db.query(Story).filter(Story.title.contains("снимком звёзд")).one()
    star_rank = (
        db.query(RankedCandidate)
        .join(StoryCluster, StoryCluster.id == RankedCandidate.cluster_id)
        .filter(StoryCluster.cluster_key == stars.cluster_id, RankedCandidate.channel_id == "github")
        .one()
    )
    assert star_rank.dimensions_json["trend_signal"] is None
    assert "неизвестен" in star_rank.explanation
    primary = [row for row in ranked if row.channel_id == cluster.primary_channel_id and row.cluster_id == cluster.id][0]
    other = [row for row in ranked if row.channel_id != cluster.primary_channel_id and row.cluster_id == cluster.id]
    assert other and other[0].rank_score < primary.rank_score
    assert db.query(StoryCluster).filter_by(list_name="backfill").count() > 0
    assert db.query(StoryCluster).filter_by(kind="cve", list_name="review").count() == 1
    again = import_observations(db, build_pack(), NOW)
    assert again["created"] == 0
    assert again["duplicates"] == 162
    assert db.query(Story).count() == 160
    assert db.query(SourceItem).count() == 162


def test_g2_drafts_are_checkable_and_not_published(db):
    _stats, made = _load(db)
    assert made == 24
    assert db.query(Post).filter_by(synthetic=True).count() == 24
    cyber = db.query(Post).filter_by(channel_id="cyber").all()
    assert cyber and all(post.approvals_required == 2 for post in cyber)
    assert all("не сводка по всем установкам" in post.body for post in cyber)
    assert all("CVSS" not in post.body for post in cyber)
    snapshots = db.query(EvidenceSnapshot).all()
    assert snapshots
    assert all(row.verified_at is None and row.support_level == "source_supported" for row in snapshots)
    assert all(row.origin_kind == "source_claim" for row in snapshots)
    preprint = db.query(Story).filter_by(is_preprint=True).one()
    post = db.query(Post).filter_by(story_id=preprint.id).one()
    value = [item for item in variants_for(db, post) if item["angle"] == "value"][0]
    assert "препринт не равен рецензии" in value["body"]
    github = db.query(Post).filter_by(channel_id="github").first()
    apply = [item for item in variants_for(db, github) if item["angle"] == "apply"][0]
    assert "не подтверждена" in apply["body"]
    assert "MIT" not in apply["body"]
    broken = fallback_from_invalid("dev", "DEMO")
    assert broken["llm_fallback"] is True
    assert broken["requires_review"] is True
    assert db.query(PublishingOutbox).count() == 0


def test_g3_studio_layouts_and_rights(db, tmp_path):
    channels = db.query(Channel).order_by(Channel.id).all()
    paths = write_studio_pack(tmp_path, channels)
    assert len(paths) == 40
    hashes = set()
    for path in paths:
        payload = path.read_bytes()
        assert payload[:2] == b"\xff\xd8"
        with Image.open(BytesIO(payload)) as image:
            assert image.size == (1280, 720)
        hashes.add(hashlib.sha256(payload).hexdigest())
    assert len(hashes) == 40
    channel = channels[0]
    card = render_network_card(
        channel_id=channel.id,
        channel_title=channel.title,
        primary="#112233",
        accent="#44ddaa",
        template_id="hero",
        title="DEMO: короткий заголовок",
        subtitle="одна строка",
        demo=True,
    )
    assert card.layout.fits is True
    assert len(card.layout.lines) <= 2
    chosen, basis = choose_rights(b"not-an-image", "unknown", True, card)
    assert basis == "own_typographic_template"
    assert chosen.sha256 == card.sha256


def test_g4_pages_and_routes(db, client):
    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    create_user(db, username="editor", password="editor-password-1", role="EDITOR")
    db.commit()
    denied = client.post("/api/v1/demo/load")
    assert denied.status_code == 401
    editor = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
    editor_token = editor.json()["csrf_token"]
    blocked = client.post("/api/v1/demo/load", headers={"x-csrf-token": editor_token})
    assert blocked.status_code == 403
    owner = client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    token = owner.json()["csrf_token"]
    loaded = client.post("/api/v1/demo/load", headers={"x-csrf-token": token})
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["data_mode"] == "demo"
    assert body["posts"] == 24
    radar = client.get("/radar?channel=cyber")
    assert radar.status_code == 200
    assert "CVE-2026-990099" in radar.text
    assert "trend_signal" in radar.text or "Канал" in radar.text
    overview = client.get("/")
    assert overview.status_code == 200
    assert "НейроПульс" in overview.text
    assert "н/д" in overview.text
    posts = client.get("/posts?channel=ai_news")
    assert posts.status_code == 200
    review_id = db.query(Post).filter_by(channel_id="ai_news").first().id
    review = client.get(f"/review/{review_id}")
    assert review.status_code == 200
    assert "проверено" in review.text
    studio = client.get("/studio")
    assert studio.status_code == 200
    assert studio.text.count("<img") == 48
    calendar = client.get("/calendar")
    assert calendar.status_code == 200
    assert "Europe/Moscow" in calendar.text or "MSK" in calendar.text
    analytics = client.get("/analytics")
    assert analytics.status_code == 200
    assert "н/д" in analytics.text
    commercial = client.get("/commercial")
    assert commercial.status_code == 200
    assert "DEMO" in commercial.text
    system = client.get("/system")
    assert system.status_code == 200
    assert "FEATURE_RADAR_V2" in system.text
    sponsored = client.post("/api/v1/system/sponsored", headers={"x-csrf-token": token})
    assert sponsored.status_code == 403


def test_g5_calendar_does_not_invent_or_publish(db):
    _load(db)
    report = propose_fortnight(db, NOW)
    assert report["published"] == 0
    assert report["created"] > 0
    assert db.query(Episode).filter(Episode.status != "proposed").count() == 0
    assert db.query(Post).filter_by(review_status="PUBLISHED").count() == 0
    empty = propose_fortnight(db, NOW)
    assert empty["created"] == 0 or empty["conflicts"]
    assert report.get("horizon_days") == 28
    used: list[int] = []
    for episode in db.query(Episode):
        used.extend(int(item) for item in (episode.item_refs or []) if str(item).isdigit())
    assert used
    assert len(used) == len(set(used))
    channel = db.get(Channel, "future")
    assert _quiet(NOW.replace(hour=23), channel.quiet_start, channel.quiet_end) is True
    assert _quiet(NOW.replace(hour=10), channel.quiet_start, channel.quiet_end) is False
    episode = db.query(Episode).first()
    other = db.query(Episode).filter(Episode.id != episode.id, Episode.channel_id == episode.channel_id).first()
    try:
        move_episode(db, episode, other.slot_utc, episode.version)
        raise AssertionError("occupied slot was overwritten")
    except ValueError as exc:
        assert str(exc) == "slot_conflict"
    db.refresh(episode)
    try:
        move_episode(db, episode, episode.slot_utc + timedelta(days=40), episode.version + 3)
        raise AssertionError("stale version was accepted")
    except ValueError as exc:
        assert str(exc) == "version_conflict"


def test_g5_thin_series_stays_empty(db):
    report = propose_fortnight(db, NOW)
    assert report["created"] == 0
    assert any(row["reason"] == "not_enough_material" for row in report["skipped"])
    assert db.query(Post).count() == 0


def test_g6_funnel_and_demo_money_stay_separate(db):
    _load(db)
    seed_demo_campaigns(db, NOW)
    report = funnel(db, now=NOW)
    assert report["data_mode"] == "measured"
    assert report["views"] == "н/д"
    assert report["members"] == "н/д"
    assert report["stages"]["published"] == 0
    assert report["stages"]["ingested"] == 162
    campaigns = db.query(AdCampaign).filter_by(demo=True).all()
    assert len(campaigns) == 2
    actuals = db.query(FinanceEvent).filter_by(kind="actual").all()
    assert actuals and all(row.amount is None for row in actuals)
    flags = db.query(RuntimeSetting).filter(RuntimeSetting.key.like("FEATURE_%")).all()
    assert len(flags) == 5
    assert all(row.value_json["value"] is True for row in flags)
    settings = make_settings()
    assert settings.source_mode == "offline"
    assert settings.sponsored_enabled is False


def test_sec_dispatcher_blocks_synthetic_and_detects_edits(db, engine):
    settings = make_settings()
    assert build_telegram_transport(settings) is None
    _load(db)
    post = db.query(Post).filter_by(synthetic=True).first()
    channel = db.get(Channel, post.channel_id)
    channel.chat_id = "100"
    outbox = PublishingOutbox(
        post_id=post.id,
        channel_id=post.channel_id,
        due_utc=NOW,
        idempotency_key="demo-block",
        state="scheduled",
        caption_hash=post.caption_hash,
    )
    db.add(outbox)
    db.commit()
    transport = ScriptedTransport([TgResult(200, message_id="1")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, media_dir=MEDIA)
    assert result["calls"] == 0
    assert result["reason"] == "synthetic_never_publish"
    assert transport.calls == []
    assert db.query(PublishedMessage).count() == 0

    live, _owner, editor = approved_post(db)
    live_channel = db.get(Channel, live.channel_id)
    live_channel.chat_id = "100"
    db.add(refresh_card(live, live_channel, MEDIA))
    db.commit()
    scheduled = schedule_post(db, live, editor, due=NOW, confirmed=True, now=NOW)
    claimed = live.caption
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    seen = {}

    def send(payload):
        seen["caption"] = payload["caption"]
        other = factory()
        row = other.get(Post, live.id)
        row.caption = row.caption + " правка"
        row.caption_hash = hashlib.sha256(row.caption.encode()).hexdigest()
        row.draft_version += 1
        other.commit()
        other.close()
        return TgResult(200, message_id="555")

    transport = ScriptedTransport([TgResult(200, message_id="555")])
    transport.send_photo = send
    changed = dispatch_outbox(db, scheduled, transport, now=NOW, media_dir=MEDIA)
    assert changed["reason"] == "content_changed_during_send"
    assert seen["caption"] == claimed
    db.refresh(scheduled)
    assert scheduled.state == "needs_reconciliation"
    assert db.query(PublishedMessage).count() == 0


def test_ops01_upgrade_keeps_existing_story():
    name = "tmn_global_mig"
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"])
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"CREATE DATABASE {name} OWNER tmn"])
    url = f"postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/{name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "0003_r7_integrity"], cwd=ROOT_DIR, env=env)
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE publishing_outbox DROP COLUMN IF EXISTS claimed_draft_version"))
        conn.execute(text("ALTER TABLE publishing_outbox DROP COLUMN IF EXISTS claimed_caption"))
        conn.execute(text("ALTER TABLE ad_campaigns DROP COLUMN IF EXISTS demo"))
        conn.execute(text("DROP TABLE IF EXISTS story_clusters CASCADE"))
        conn.execute(
            text(
                """
                INSERT INTO stories (
                    canonical_url, canonical_hash, cluster_id, repo_identity, title, summary,
                    status, provenance_json, primary_channel_id, score_total, score_band,
                    hard_block_reason, content_kind, license_state, license_spdx, source_id,
                    synthetic, is_preprint, discovered_utc
                ) VALUES (
                    'https://example.com/kept', 'kept', 'kept', '', 'kept-row', '',
                    'INGESTED', '{}', '', 0, '',
                    '', 'news', 'unknown', '', '',
                    false, false, now()
                )
                """
            )
        )
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT_DIR, env=env)
    with engine.connect() as conn:
        kept = conn.execute(text("SELECT title FROM stories WHERE title = 'kept-row'")).scalar()
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        clusters = conn.execute(text("SELECT to_regclass('public.story_clusters')")).scalar()
        column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'publishing_outbox' AND column_name = 'claimed_draft_version'"
            )
        ).scalar()
    engine.dispose()
    assert kept == "kept-row"
    assert version == "0006_r10_media_os"
    assert clusters == "story_clusters"
    assert column == 1


def test_manual_list_survives_rerank(db):
    _load(db)
    cluster = db.query(StoryCluster).filter_by(list_name="hot").first()
    from app.product.radar import bulk_list

    bulk_list(db, [cluster.id], "rejected", "не наш формат", "owner")
    db.commit()
    rank_open_clusters(db, NOW)
    db.commit()
    db.refresh(cluster)
    assert cluster.list_name == "rejected"
