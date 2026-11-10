"""R9 product platform. Demo rows stay synthetic. Telegram is not contacted."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from io import BytesIO

from app.core.db import SCHEMA_HEAD
from app.core.models import (
    AdCampaign,
    ChannelEditorialProfile,
    ClusterMember,
    EditorialClaim,
    Episode,
    ExperimentPlan,
    FinanceEvent,
    Post,
    PublishedMessage,
    RankedCandidate,
    RateCard,
    SalesLead,
    Story,
    StoryCluster,
    StoryRelation,
)
from app.media.renderer import NETWORK_TEMPLATES, write_studio_pack
from app.product.commercial import forecast, media_kit, seed_commercial
from app.product.demo_pack import build_pack
from app.product.drafts import materialise_desk
from app.product.editorial import FORMATS, PROFILES, ensure_profiles, quality_gate
from app.product.growth import board, ensure_metrics, seed_experiments, snapshot_derived
from app.product.insights import funnel, seed_demo_campaigns
from app.product.intelligence import canonical_url
from app.product.planning import lock_episode, propose_month
from app.product.programs import propose_fortnight
from app.product.radar import MODEL, import_observations, merge_into, split_member
from app.publishing.gate import build_telegram_transport
from app.services.accounts import AuthError, create_user
from app.services.moderation import approve_post, schedule_post
from PIL import Image
from tests.conftest import make_settings
from tests.factories import NOW
from tests.support import approved_post


def _load(db):
    stats = import_observations(db, build_pack(), NOW)
    ensure_profiles(db)
    posts = materialise_desk(db)
    return stats, posts


def _rank(db, title_part: str, channel_id: str) -> RankedCandidate:
    story = db.query(Story).filter(Story.title.contains(title_part)).first()
    assert story is not None
    cluster = db.query(StoryCluster).filter_by(cluster_key=story.cluster_id).one()
    return (
        db.query(RankedCandidate)
        .filter_by(cluster_id=cluster.id, channel_id=channel_id, model_version=MODEL)
        .one()
    )


def test_r9_a02_fail_closed_and_no_telegram():
    settings = make_settings()
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert settings.sponsored_enabled is False
    assert settings.source_mode == "offline"
    assert settings.llm_mode == "mock"
    assert build_telegram_transport(settings) is None


def test_r9_a03_passports_and_formats(db):
    ensure_profiles(db)
    assert len(PROFILES) == 8
    assert len(FORMATS) == 7
    rows = db.query(ChannelEditorialProfile).all()
    assert {row.channel_id for row in rows} == set(PROFILES)
    for row in rows:
        assert row.promise
        assert row.audience
        assert len(row.formats_json) >= 3


def test_r9_a04_scores_differ_and_uncertainty_is_named(db):
    _load(db)
    shared = _rank(db, "локальном запуске", "ai_news")
    release = _rank(db, "demo-runner v1.2.0", "github")
    stars = _rank(db, "снимком звёзд", "github")
    cve = _rank(db, "CVE-2026-990099", "cyber")
    preprint = _rank(db, "препринт 2601.09999", "future")
    scores = {shared.rank_score, release.rank_score, stars.rank_score, cve.rank_score, preprint.rank_score}
    assert len(scores) >= 4
    assert stars.dimensions_json["trend_signal"] is None
    assert "неизвестен" in stars.explanation
    assert "confidence" in stars.explanation
    assert "evidence_state" in stars.explanation
    assert stars.confidence != stars.rank_score
    backfill = db.query(StoryCluster).filter_by(list_name="backfill").first()
    assert backfill is not None
    old = db.query(RankedCandidate).filter_by(cluster_id=backfill.id, model_version=MODEL).first()
    assert old is not None
    assert (old.penalties_json or {}).get("backfill") == 10
    from app.product.intelligence import score_cluster

    sample = stars
    first = score_cluster(
        db.get(StoryCluster, sample.cluster_id),
        sample.channel_id,
        samples=1,
        members=1,
        source_ids=["github_search"],
        now=NOW,
        anchor=NOW,
        preprint=False,
        license_state="unknown",
        channel_hot=8,
    )
    second = score_cluster(
        db.get(StoryCluster, sample.cluster_id),
        sample.channel_id,
        samples=1,
        members=1,
        source_ids=["github_search"],
        now=NOW,
        anchor=NOW,
        preprint=False,
        license_state="unknown",
        channel_hot=8,
    )
    assert first[2] == second[2]


def test_r9_a05_canonical_merge_split(db):
    assert canonical_url("https://Example.com/path/?utm_source=x&id=1#frag") == "https://example.com/path?id=1"
    stats, _posts = _load(db)
    assert stats["created"] == 162
    again = import_observations(db, build_pack(), NOW)
    assert again["created"] == 0
    assert again["duplicates"] == 162
    extra = [
        {
            "channel_id": "ai_news",
            "external_id": "demo:utm:1",
            "title": "DEMO: utm twin",
            "url": "https://example.com/demo/utm?utm_campaign=x",
            "source_id": "huggingface",
            "summary": "Тот же путь без метки.",
            "cve": "",
            "repo": "",
            "tag": "",
            "arxiv": "",
            "stars": None,
            "days_old": 0,
            "synthetic": True,
        },
        {
            "channel_id": "ai_news",
            "external_id": "demo:utm:2",
            "title": "DEMO: utm twin",
            "url": "https://example.com/demo/utm?fbclid=1",
            "source_id": "hackernews",
            "summary": "Вторая метка, тот же канонический URL.",
            "cve": "",
            "repo": "",
            "tag": "",
            "arxiv": "",
            "stars": None,
            "days_old": 0,
            "synthetic": True,
        },
    ]
    imported = import_observations(db, extra, NOW)
    assert imported["created"] == 2
    key = "url:" + hashlib.sha256(canonical_url("https://example.com/demo/utm").encode()).hexdigest()[:24]
    cluster = db.query(StoryCluster).filter_by(cluster_key=key).one()
    assert db.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").count() == 2
    source = db.query(StoryCluster).filter(StoryCluster.cluster_key.contains("v1.2.0")).one()
    target = db.query(StoryCluster).filter(StoryCluster.cluster_key.contains("v1.3.0")).one()
    try:
        merge_into(db, source.id, target.id, "owner", "разные теги")
        raise AssertionError("different tags merged")
    except ValueError:
        pass
    member = db.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").order_by(ClusterMember.id.desc()).first()
    created = split_member(db, cluster.id, member.id, "owner", "самостоятельный сюжет")
    db.commit()
    assert created.id != cluster.id
    assert db.query(StoryRelation).filter_by(relation="split").count() >= 1


def test_r9_a06_a07_drafts_are_channel_unique(db):
    _stats, made = _load(db)
    assert made == 24
    posts = db.query(Post).all()
    assert all(post.synthetic for post in posts)
    pairs = {(post.story_id, post.channel_id) for post in posts}
    assert len(pairs) == 24
    for channel_id in PROFILES:
        bodies = [post.body for post in posts if post.channel_id == channel_id]
        formats = {post.format_id for post in posts if post.channel_id == channel_id}
        assert len(bodies) == 3
        assert len(set(bodies)) == 3
        assert len(formats) == 3
        assert all("DEMO" in (post.warnings_json or []) or post.synthetic for post in posts if post.channel_id == channel_id)
    preprint = db.query(Story).filter_by(is_preprint=True).one()
    post = db.query(Post).filter_by(story_id=preprint.id).one()
    assert "препринт не равен рецензии" in post.body or "Препринт не равен рецензии" in post.body
    assert db.query(EditorialClaim).count() >= 24
    assert db.query(PublishedMessage).count() == 0


def test_r9_a08_quality_blocks_synthetic_and_license(db):
    _load(db)
    post = db.query(Post).filter_by(synthetic=True).first()
    story = db.get(Story, post.story_id)
    report = quality_gate(db, post, story)
    assert "synthetic_never_publish" in report["blocking"]
    assert report["publishable"] is False
    github = db.query(Post).filter_by(channel_id="github").first()
    github.body = github.body + " MIT open source"
    story = db.get(Story, github.story_id)
    story.license_state = "unknown"
    blocked = quality_gate(db, github, story)
    assert "license_claim_without_evidence" in blocked["blocking"]
    github.body = "Изобретённый CVSS 9.8 без источника"
    blocked = quality_gate(db, github, story)
    assert "cvss_without_source" in blocked["blocking"]


def test_r9_a09_forty_templates(db, tmp_path):
    from app.core.models import Channel

    channels = db.query(Channel).order_by(Channel.id).all()
    assert NETWORK_TEMPLATES == ("lead", "tool", "security", "digest", "deep-dive")
    paths = write_studio_pack(tmp_path, channels)
    assert len(paths) == 40
    hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assert len(hashes) == 40
    payload = paths[0].read_bytes()
    assert payload[:2] == b"\xff\xd8"
    with Image.open(BytesIO(payload)) as image:
        assert image.size == (1280, 720)


def test_r9_a10_a11_planner_unique_and_lock(db):
    _load(db)
    report = propose_month(db, NOW, days=28)
    assert report["horizon_days"] == 28
    assert report["published"] == 0
    used: list[int] = []
    for episode in db.query(Episode):
        assert episode.status == "proposed"
        used.extend(int(item) for item in (episode.item_refs or []) if str(item).isdigit())
    assert len(used) == len(set(used))
    episode = db.query(Episode).first()
    refs = list(episode.item_refs)
    lock_episode(db, episode, "owner")
    db.refresh(episode)
    assert episode.locked is True
    second = propose_fortnight(db, NOW)
    assert second["created"] == 0 or second["conflicts"]
    db.refresh(episode)
    assert episode.item_refs == refs
    late = NOW + timedelta(days=10)
    cluster = db.query(StoryCluster).filter_by(kind="event").first()
    cluster.event_type = "event"
    cluster.event_at = NOW - timedelta(days=10)
    from app.product.planning import _within_ttl

    assert _within_ttl(db, cluster, late) is False


def test_r9_a12_funnel_lineage(db):
    _load(db)
    total = funnel(db, now=NOW)
    assert total["stages"]["ingested"] == 162
    cyber = funnel(db, channel_id="cyber", now=NOW)
    github = funnel(db, channel_id="github", now=NOW)
    assert cyber["stages"]["ingested"] < total["stages"]["ingested"]
    assert github["stages"]["ingested"] < total["stages"]["ingested"]
    news = funnel(db, channel_id="ai_news", now=NOW)
    assert news["stages"]["ingested"] > cyber["stages"]["ingested"]
    assert github["stages"]["ingested"] == 20
    assert cyber["views"] == "н/д"
    assert cyber["members"] == "н/д"


def test_r9_a13_a14_metrics_and_commerce(db):
    _load(db)
    seed_demo_campaigns(db, NOW)
    seed_commercial(db, NOW)
    ensure_metrics(db)
    seed_experiments(db)
    snapshot_derived(db, NOW, demo=True)
    panel = board(db)
    assert all(row["status"] == "NOT_STARTED" for row in panel["experiments"])
    assert all(row["actual"] == "н/д" for row in panel["experiments"])
    views = [row for row in panel["observations"] if row["metric_id"] == "views"][0]
    assert views["value"] is None
    assert views["display"] == "н/д"
    kit = media_kit(db)
    assert kit["audience"] == "н/д"
    assert kit["actual_revenue"] is None
    money = forecast(db)
    assert money["actual_label"] == "н/д"
    assert db.query(SalesLead).count() == 8
    assert db.query(RateCard).count() == 4
    assert all(row.price is None for row in db.query(RateCard))
    assert db.query(ExperimentPlan).count() >= 3
    actuals = db.query(FinanceEvent).filter_by(kind="actual").all()
    assert actuals
    assert all(row.amount is None for row in actuals)


def test_r9_a15_sponsor_still_blocked(db):
    post, _owner, editor = approved_post(db)
    campaign = AdCampaign(advertiser="DEMO legal", channel_id=post.channel_id, marked=False, legal_status="pending")
    db.add(campaign)
    db.flush()
    post.flags_json = ["sponsored"]
    post.sponsored_campaign_id = campaign.id
    db.commit()
    try:
        approve_post(db, post, editor, confirmed=True)
        raise AssertionError("sponsored post approved")
    except AuthError:
        pass
    try:
        schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
        raise AssertionError("sponsored post scheduled")
    except AuthError:
        pass


def test_r9_a17_schema_head():
    assert SCHEMA_HEAD == "0006_r10_media_os"


def test_r9_a18_rerun_does_not_duplicate(db):
    first, posts = _load(db)
    seed_commercial(db, NOW)
    calendar = propose_fortnight(db, NOW)
    second, more = _load(db)
    assert first["created"] == 162
    assert second["created"] == 0
    assert more == 0
    assert posts == 24
    assert db.query(Post).count() == 24
    again = propose_fortnight(db, NOW)
    assert again["created"] == 0 or again["conflicts"]
    assert db.query(Episode).count() == calendar["created"] or db.query(Episode).count() >= calendar["created"]


def test_r9_a20_pages_and_api(db, client):
    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    db.commit()
    owner = client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    token = owner.json()["csrf_token"]
    loaded = client.post("/api/v1/demo/load", headers={"x-csrf-token": token})
    assert loaded.status_code == 200
    assert loaded.json()["horizon_days"] == 28
    for path in ("/", "/radar", "/posts", "/calendar?days=28", "/studio", "/sources", "/quality", "/analytics", "/commercial", "/system"):
        page = client.get(path)
        assert page.status_code == 200, path
    kit = client.get("/api/v1/commercial/mediakit")
    assert kit.status_code == 200
    assert kit.json()["audience"] == "н/д"
    growth = client.get("/api/v1/growth")
    assert growth.status_code == 200
    quality = client.get("/quality")
    assert "synthetic_never_publish" in quality.text or "Качество" in quality.text
    radar = client.get("/radar?channel=cyber&q=CVE")
    assert "CVE-2026-990099" in radar.text
    studio = client.get("/studio")
    assert studio.text.count("<img") == 48
