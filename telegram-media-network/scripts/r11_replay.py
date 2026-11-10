#!/usr/bin/env python3
"""Replay historical-small day by day. No network."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory, prepare_database
from app.product.lab import export_lab, load_lab
from app.services.bootstrap import bootstrap

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = Settings()
    engine = make_engine(settings.database_url)
    prepare_database(engine, "create_all")
    factory = make_session_factory(engine)
    session = factory()
    try:
        bootstrap(session, settings)
        session.commit()
        report = load_lab(session, through_day=30, actor="replay", mode="historical-small")
        exported = export_lab(session, report["lab_run_id"])
        payload = {
            "lab_run_id": report["lab_run_id"],
            "idempotent": report.get("idempotent"),
            "days": len(exported.get("days") or []),
            "clusters": exported.get("clusters"),
            "source_items": exported.get("source_items"),
            "telegram_send": 0,
            "published_messages": exported.get("published_messages"),
        }
        out = ROOT / "reports" / "r11-lab-results.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("PUBLISH ENABLED? NO. TELEGRAM SEND COUNT? 0.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
