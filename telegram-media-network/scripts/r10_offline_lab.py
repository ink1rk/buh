"""Offline 30-day lab. No Telegram, no live HTTP."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory, prepare_database
from app.core.timeutil import utcnow
from app.product.lab import export_lab, load_lab, tick_day
from app.publishing.gate import build_telegram_transport
from app.services.bootstrap import bootstrap

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = Settings(
        environment="development",
        dry_run=True,
        publish_enabled=False,
        global_kill_switch=True,
        sponsored_enabled=False,
        source_mode="offline",
        llm_mode="mock",
    )
    engine = make_engine(settings.database_url)
    prepare_database(engine, "create_all")
    factory = make_session_factory(engine)
    session = factory()
    try:
        bootstrap(session, settings)
        session.commit()
        report = load_lab(session, through_day=30, actor="lab")
        again = load_lab(session, through_day=30, actor="lab")
        days = {f"day_{day}": tick_day(session, day) for day in (1, 15, 30)}
        exported = export_lab(session)
        payload = {
            "as_of": utcnow().isoformat(),
            "transport": None if build_telegram_transport(settings) is None else "present",
            "telegram_send": 0,
            "first": report,
            "second_idempotent": again.get("idempotent"),
            "days": days,
            "export": exported,
            "production_ready": False,
        }
        out = ROOT / "reports" / "lab-results.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md = ROOT / "reports" / "R10_OFFLINE_LAB_REPORT.md"
        md.write_text(
            "\n".join(
                [
                    "# R10 offline lab",
                    "",
                    f"Прогон `{report.get('lab_run_id')}`, повтор идемпотентен: `{again.get('idempotent')}`.",
                    f"Telegram send: 0. Published: {exported.get('published_messages')}.",
                    f"Сюжеты: {exported.get('clusters')}. Посты по каналам: {exported.get('channels')}.",
                    "",
                    "PRODUCTION READY: NO",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"lab_run_id": report.get("lab_run_id"), "idempotent": again.get("idempotent"), "telegram_send": 0}))
    finally:
        session.close()


if __name__ == "__main__":
    main()
