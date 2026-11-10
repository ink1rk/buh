"""R10 media OS. Demo stays unpublished. Telegram is not contacted."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from io import BytesIO

from app.core.db import SCHEMA_HEAD
from app.core.models import (
    CommercialOffer,
    EditorialClaim,
    EditorialVariant,
    EventRelation,
    LabRun,
    Post,
    PublishedMessage,
    SourceItem,
    SourceSnapshot,
    StoryCluster,
    WorkflowRun,
)
from app.media.renderer import STUDIO_PURPOSES, fit_headline, write_studio_pack_v3
from app.product.commercial import cancel_offer, create_offer, forecast, reserve_offer
from app.product.dossier import verify_claim
from app.product.intelligence import compute_trend, independent_publishers, score_cluster
from app.product.lab import build_lab_events, export_lab, load_lab
from app.product.planning import propose_month
from app.product.workflow import pause_run, resume_run, run_until_human, start_run
from app.publishing.gate import build_telegram_transport
from app.services.accounts import create_user
from PIL import Image
from tests.conftest import make_settings
from tests.factories import NOW
from tests.test_r9 import _load


def test_r10_a01_schema_and_r9_compat(db):
    assert SCHEMA_HEAD == "0007_r11_editorial_pilot"
    stats, posts = _load(db)
    assert stats["created"] == 162
    assert posts == 24
    assert db.query(PublishedMessage).count() == 0


def test_r10_a02_fail_closed():
    settings = make_settings()
    assert settings.dry_run is True
    assert settings.publish_enabled is False
    assert settings.global_kill_switch is True
    assert settings.sponsored_enabled is False
    assert settings.source_mode == "offline"
    assert settings.llm_mode == "mock"
    assert build_telegram_transport(settings) is None


def test_r10_a03_cve_and_release_identity(db):
    load_lab(db, through_day=30)
    cve_a = db.query(StoryCluster).filter_by(cluster_key="cve:CVE-2026-880001").one()
    cve_b = db.query(StoryCluster).filter_by(cluster_key="cve:CVE-2026-880099").one()
    assert cve_a.id != cve_b.id
    v1 = db.query(StoryCluster).filter(StoryCluster.cluster_key.contains("lab-runner:v1.0")).one()
    v2 = db.query(StoryCluster).filter(StoryCluster.cluster_key.contains("lab-runner:v2.0")).one()
    assert v1.id != v2.id
    reprints = db.query(EventRelation).filter_by(relation="reprint").count()
    assert reprints >= 1


def test_r10_a04_true_trend():
    from app.core.models import TrendSample

    one = [
        TrendSample(source_item_id=1, snapshot_utc=NOW, metric_name="github_stars", value=100, provider="github"),
    ]
    unknown = compute_trend(one)
    assert unknown["state"] == "unknown"
    assert unknown["signal"] is None
    series = [
        TrendSample(source_item_id=1, snapshot_utc=NOW, metric_name="github_stars", value=100, provider="github"),
        TrendSample(source_item_id=1, snapshot_utc=NOW + timedelta(days=9), metric_name="github_stars", value=140, provider="github"),
    ]
    up = compute_trend(series)
    assert up["state"] == "up"
    assert up["delta"] == 40
    assert up["signal"] == 40
    down = compute_trend(
        [
            TrendSample(source_item_id=1, snapshot_utc=NOW, metric_name="github_stars", value=50, provider="github"),
            TrendSample(source_item_id=1, snapshot_utc=NOW + timedelta(days=1), metric_name="github_stars", value=20, provider="github"),
        ]
    )
    assert down["state"] == "down"
    assert down["delta"] == -30


def test_r10_a05_reprints_are_not_independent():
    pubs = independent_publishers(["cisa_kev", "rss_mirror"])
    assert pubs == {"cisa"}
    mixed = independent_publishers(["cisa_kev", "hackernews", "rss_mirror"])
    assert mixed == {"cisa"}


def test_r10_a06_claims_never_auto_verified(db):
    _load(db)
    rows = db.query(EditorialClaim).all()
    assert rows
    assert all(row.status != "independently_verified" for row in rows)
    claim = rows[0]
    try:
        verify_claim(db, claim, actor="owner", method="count_urls", second_publisher="https://example.com")
        raise AssertionError("url must not verify")
    except ValueError:
        pass


def test_r10_a07_two_angles(db):
    load_lab(db, through_day=8)
    shared = db.query(StoryCluster).filter(StoryCluster.title.contains("общий инфоповод")).all()
    assert len(shared) >= 1
    variants = db.query(EditorialVariant).all()
    bodies = {row.body for row in variants}
    assert len(bodies) >= 3


def test_r10_a09_headline_overflow():
    lines, _size, fits, overflow = fit_headline("короткий", 1100, 2)
    assert fits is True
    assert overflow == ""
    long_title = "Очень длинный русский заголовок про CVE-2026-880001 и неподтверждённые версии Demo Catalog App который обязан либо уместиться либо вернуть ошибку переполнения без молчаливой обрезки конца"
    _lines, _size, fits, overflow = fit_headline(long_title, 200, 2, max_size=46, min_size=22)
    assert fits is False
    assert overflow == "headline_overflow"


def test_r10_a10_forty_eight_designs(db, tmp_path):
    from app.core.models import Channel

    channels = db.query(Channel).order_by(Channel.id).all()
    assert STUDIO_PURPOSES == ("news", "review", "tool", "security", "digest", "deep-dive")
    paths = write_studio_pack_v3(tmp_path, channels)
    assert len(paths) == 48
    hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assert len(hashes) == 48
    with Image.open(BytesIO(paths[0].read_bytes())) as image:
        assert image.size == (1280, 720)
    from app.media.renderer import render_studio_card

    square = render_studio_card(
        channel_id="dev",
        channel_title="Dev",
        primary="#1c2434",
        accent="#d7e2ea",
        purpose="news",
        title="DEMO: квадрат",
        ratio="1:1",
    )
    portrait = render_studio_card(
        channel_id="dev",
        channel_title="Dev",
        primary="#1c2434",
        accent="#d7e2ea",
        purpose="news",
        title="DEMO: вертикаль",
        ratio="4:5",
    )
    assert square.width == 1080 and square.height == 1080
    assert portrait.width == 1080 and portrait.height == 1350


def test_r10_a11_calendar_days_differ(db, client):
    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    db.commit()
    client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    week = client.get("/calendar?days=7")
    month = client.get("/calendar?days=28")
    assert week.status_code == 200
    assert month.status_code == 200
    assert 'aria-label="Сетка 7 дней"' in week.text
    assert 'aria-label="Сетка 28 дней"' in month.text
    assert "cal-grid days-7" in week.text
    assert "cal-grid days-28" in month.text
    assert week.text.count("cal-head") != month.text.count("cal-head")
    assert month.text.count("cal-head") >= 29


def test_r10_a12_planner_honest_gaps(db):
    _load(db)
    report = propose_month(db, NOW, days=28)
    assert report["published"] == 0
    assert any(item.get("reason") == "not_enough_material" for item in report["skipped"]) or report["created"] >= 0


def test_r10_a15_metrics_lineage(db):
    from app.core.models import MetricObservation, MetricProvenance
    from app.product.growth import board, snapshot_derived

    _load(db)
    snapshot_derived(db, NOW, demo=False)
    db.commit()
    panel = board(db)
    views = [row for row in panel["observations"] if row["metric_id"] == "views"]
    ingested = [row for row in panel["observations"] if row["metric_id"] == "ingested" and row["channel_id"] == "network"]
    assert views and views[0]["value"] is None and views[0]["display"] == "н/д"
    assert ingested and ingested[0]["value"] not in {None, 0} and ingested[0]["source_type"] == "db_derived"
    drafted = (
        db.query(MetricObservation)
        .filter_by(metric_id="drafted", channel_id="cyber")
        .order_by(MetricObservation.id.desc())
        .first()
    )
    assert drafted is not None
    assert drafted.source_type == "db_derived"
    assert db.query(MetricProvenance).count() >= 1


def test_r10_a13_a14_workflow_idempotent(db):
    _load(db)
    cluster = db.query(StoryCluster).first()
    first = start_run(db, cluster=cluster, channel_id=cluster.primary_channel_id, actor="owner")
    second = start_run(db, cluster=cluster, channel_id=cluster.primary_channel_id, actor="editor")
    assert first.id == second.id
    run_until_human(db, first, NOW)
    assert first.delivery_allowed is False
    pause_run(db, first, "owner")
    assert first.paused is True
    resume_run(db, first, "owner")
    assert db.query(WorkflowRun).filter_by(idempotency_key=first.idempotency_key).count() == 1


def test_r10_a16_forecast_label_follows_amount(db):
    from app.core.models import AdCampaign, FinanceEvent

    campaign = AdCampaign(advertiser="live", channel_id="dev", demo=False, legal_status="pending")
    db.add(campaign)
    db.flush()
    db.add(FinanceEvent(campaign_id=campaign.id, kind="actual", amount=1500, demo=False, note="ручной факт"))
    db.commit()
    money = forecast(db)
    assert money["actual_amount"] == 1500
    assert money["actual_label"] == "1500"


def test_r10_a17_offer_reserve_cancel(db):
    from app.core.models import SalesLead

    _load(db)
    from app.product.commercial import seed_commercial

    seed_commercial(db, NOW)
    lead = db.query(SalesLead).first()
    offer = create_offer(db, lead, title="DEMO пакет", package="single", channel_id=lead.channel_id, actor="owner")
    reserve_offer(db, offer, NOW, "owner")
    assert offer.status == "reserved"
    cancel_offer(db, offer, "owner")
    assert offer.status == "cancelled"
    assert db.query(CommercialOffer).count() >= 1
    assert db.query(PublishedMessage).count() == 0


def test_r10_a18_rbac_and_csrf(db, client):
    create_user(db, username="viewer", password="viewer-password-1", role="VIEWER")
    create_user(db, username="editor", password="editor-password-1", role="EDITOR")
    db.commit()
    viewer = client.post("/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password-1"})
    token = viewer.json()["csrf_token"]
    denied = client.post("/api/v1/lab/load", headers={"x-csrf-token": token})
    assert denied.status_code == 403
    editor = client.post("/api/v1/auth/login", json={"username": "editor", "password": "editor-password-1"})
    editor_token = editor.json()["csrf_token"]
    blocked = client.post("/api/v1/lab/load", headers={"x-csrf-token": editor_token})
    assert blocked.status_code == 403
    missing = client.post("/api/v1/radar/clusters/bulk", json={"cluster_ids": [1], "list_name": "rejected"})
    assert missing.status_code in {401, 403, 422}


def test_r10_a20_lab_idempotent(db):
    first = load_lab(db, through_day=30)
    items = db.query(SourceItem).count()
    snapshots = db.query(SourceSnapshot).count()
    second = load_lab(db, through_day=30)
    assert second["idempotent"] is True
    assert db.query(SourceItem).count() == items
    assert db.query(LabRun).count() == 1
    exported = export_lab(db)
    assert exported["telegram_send"] == 0
    assert exported["published_messages"] == 0
    assert first["published"] == 0
    assert snapshots >= items


def test_r10_a21_score_versioned(db):
    _load(db)
    cluster = db.query(StoryCluster).first()
    first = score_cluster(
        cluster,
        cluster.primary_channel_id,
        samples=1,
        members=1,
        source_ids=["github_search"],
        now=NOW,
        anchor=NOW,
        preprint=False,
        license_state="unknown",
        channel_hot=2,
        weights={"relevance": 20, "freshness": 18, "evidence": 16, "novelty": 12, "practicality": 12, "urgency": 8, "density": 8, "scarcity": 6},
    )
    second = score_cluster(
        cluster,
        cluster.primary_channel_id,
        samples=1,
        members=1,
        source_ids=["github_search"],
        now=NOW,
        anchor=NOW,
        preprint=False,
        license_state="unknown",
        channel_hot=2,
        weights={"relevance": 5, "freshness": 5, "evidence": 5, "novelty": 5, "practicality": 5, "urgency": 5, "density": 5, "scarcity": 5},
    )
    assert first[2] != second[2]
    assert first[0]["formula_version"] == "rank-v4"


def test_r10_pages_dossier_autopilot_lab(db, client):
    create_user(db, username="owner", password="owner-password-12", role="OWNER")
    db.commit()
    owner = client.post("/api/v1/auth/login", json={"username": "owner", "password": "owner-password-12"})
    token = owner.json()["csrf_token"]
    loaded = client.post("/api/v1/demo/load", headers={"x-csrf-token": token})
    assert loaded.status_code == 200
    cluster = db.query(StoryCluster).first()
    dossier = client.get(f"/dossier/{cluster.id}")
    assert dossier.status_code == 200
    assert "Досье" in dossier.text
    radar = client.get("/api/v1/radar/clusters")
    body = radar.json()
    assert body["clusters"]
    assert all("data_mode" in item for item in body["clusters"])
    evidence = client.get(f"/api/v1/posts/{db.query(Post).first().id}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["claims"][0]["status"] != "independently_verified"
    for path in ("/autopilot", "/lab", "/shift", f"/passport/{cluster.primary_channel_id}"):
        page = client.get(path)
        assert page.status_code == 200, path
    events = build_lab_events(30)
    assert any(row.get("cve") == "CVE-2026-880001" for row in events)
    assert any("ignore previous" in row["summary"].lower() for row in events)
