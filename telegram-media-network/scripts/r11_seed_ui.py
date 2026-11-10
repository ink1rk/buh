"""Create a local owner and chronological lab for the R11 UI. No Telegram."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory, prepare_database
from app.core.models import Channel, User
from app.media.renderer import write_studio_pack_v3
from app.product.lab import load_lab
from app.services.accounts import create_user
from app.services.bootstrap import bootstrap


def main() -> None:
    settings = Settings(
        environment="development",
        dry_run=True,
        publish_enabled=False,
        global_kill_switch=True,
        sponsored_enabled=False,
        source_mode="offline",
        llm_mode="mock",
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_r11_lab"
        ),
        session_secret=os.environ.get("SESSION_SECRET", "demo-session-secret-value-32"),
    )
    engine = make_engine(settings.database_url)
    prepare_database(engine, "create_all")
    session = make_session_factory(engine)()
    try:
        bootstrap(session, settings)
        if session.query(User).filter_by(username="owner").first() is None:
            create_user(session, username="owner", password="owner-password-12", role="OWNER")
        session.commit()
        report = load_lab(session, through_day=30, actor="owner", mode="historical-small")
        cards = ROOT / "reports" / "screenshots" / "r11" / "cards"
        cards.mkdir(parents=True, exist_ok=True)
        written = write_studio_pack_v3(cards, session.query(Channel).order_by(Channel.id).all())
        print(
            {
                "owner": "ready",
                "lab_run_id": report["lab_run_id"],
                "telegram_send": 0,
                "clusters": report.get("clusters"),
                "cards": len(written),
            }
        )
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
