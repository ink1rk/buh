"""Create a local owner for the R10 UI. No Telegram."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory, prepare_database
from app.core.models import User
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
            "DATABASE_URL", "postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_r10_lab"
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
        print("owner-ready")
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
