#!/usr/bin/env python3
"""Offline R9 demonstration. No Telegram, no live sources."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.core.db import SCHEMA_HEAD, make_engine, make_session_factory, prepare_database
from app.core.models import Channel, Episode, Post, PublishedMessage
from app.core.timeutil import utcnow
from app.media.renderer import write_studio_pack
from app.product.commercial import seed_commercial
from app.product.demo_pack import build_pack
from app.product.drafts import materialise_desk
from app.product.editorial import ensure_profiles
from app.product.growth import ensure_metrics, seed_experiments, snapshot_derived
from app.product.insights import seed_demo_campaigns
from app.product.programs import propose_fortnight
from app.product.radar import import_observations
from app.publishing.gate import build_telegram_transport
from app.services.bootstrap import bootstrap


def main() -> int:
    settings = Settings(
        environment="test",
        dry_run=True,
        publish_enabled=False,
        global_kill_switch=True,
        sponsored_enabled=False,
        database_url="postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_test",
        session_secret="demo-session-secret-value-32",
        llm_mode="mock",
        source_mode="offline",
    )
    engine = make_engine(settings.database_url)
    prepare_database(engine, "create_all")
    factory = make_session_factory(engine)
    session = factory()
    bootstrap(session, settings)
    session.commit()
    moment = utcnow()
    stats = import_observations(session, build_pack(), moment)
    ensure_profiles(session)
    posts = materialise_desk(session)
    calendar = propose_fortnight(session, moment)
    campaigns = seed_demo_campaigns(session, moment)
    commercial = seed_commercial(session, moment)
    ensure_metrics(session)
    experiments = seed_experiments(session)
    metrics = snapshot_derived(session, moment, demo=True)
    cards = write_studio_pack(ROOT / "reports" / "screenshots" / "r9" / "cards", session.query(Channel).all())
    summary = {
        "schema_head": SCHEMA_HEAD,
        "telegram_transport": None if build_telegram_transport(settings) is None else "present",
        "observations": stats,
        "posts": posts,
        "episodes": calendar["created"],
        "skipped": len(calendar["skipped"]),
        "horizon_days": calendar.get("horizon_days"),
        "campaigns": campaigns,
        "commercial": commercial,
        "experiments": experiments,
        "metrics": metrics,
        "cards": len(cards),
        "published_messages": session.query(PublishedMessage).count(),
        "synthetic_posts": session.query(Post).filter_by(synthetic=True).count(),
        "proposed_only": session.query(Episode).filter(Episode.status != "proposed").count(),
        "publish_enabled": False,
        "live_data": False,
        "real_revenue": "н/д",
        "production_ready": False,
    }
    out = ROOT / "reports" / "R9_DEMO_SUMMARY.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    session.close()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
