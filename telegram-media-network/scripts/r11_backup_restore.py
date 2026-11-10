#!/usr/bin/env python3
"""Dump the R11 lab DB and restore into an isolated database. Additive check only."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.db import SCHEMA_HEAD, make_engine
from sqlalchemy import text

DUMP = ROOT / "var" / "backups" / "r11.sql"
SOURCE = os.environ.get("TMN_BACKUP_DB", "tmn_r11_lab")
ISOLATED = os.environ.get("TMN_RESTORE_DB", "tmn_r11_restore")
HOST = "127.0.0.1"
USER = "tmn"


def main() -> None:
    DUMP.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    subprocess.check_call(["pg_dump", "-h", HOST, "-U", USER, "-d", SOURCE, "-f", str(DUMP)], env=env)
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"DROP DATABASE IF EXISTS {ISOLATED} WITH (FORCE)"])
    subprocess.check_call(["sudo", "-u", "postgres", "psql", "-c", f"CREATE DATABASE {ISOLATED} OWNER {USER}"])
    subprocess.check_call(["psql", "-h", HOST, "-U", USER, "-d", ISOLATED, "-f", str(DUMP)], env=env)
    engine = make_engine(f"postgresql+psycopg://tmn:tmn_test_only@{HOST}:5432/{ISOLATED}")
    with engine.connect() as conn:
        alembic_table = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
        version = (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if alembic_table else None
        )
        snapshots = conn.execute(text("SELECT to_regclass('public.lab_daily_snapshots')")).scalar()
        posts = conn.execute(text("SELECT count(*) FROM posts")).scalar()
        clusters = conn.execute(text("SELECT count(*) FROM story_clusters")).scalar()
        published = conn.execute(text("SELECT count(*) FROM published_messages")).scalar()
        assets = conn.execute(text("SELECT count(*) FROM media_assets")).scalar()
        days = conn.execute(text("SELECT count(*) FROM lab_daily_snapshots")).scalar()
    engine.dispose()
    jpeg = list((ROOT / "var" / "media").glob("wf-*.jpg"))
    report = {
        "schema": version,
        "expected": SCHEMA_HEAD,
        "lab_daily_snapshots_table": snapshots,
        "daily_rows": int(days or 0),
        "posts": int(posts or 0),
        "clusters": int(clusters or 0),
        "assets": int(assets or 0),
        "published_messages": int(published or 0),
        "workflow_jpegs_on_disk": len(jpeg),
        "dump_bytes": DUMP.stat().st_size,
        "telegram_send": 0,
    }
    print(report)
    if version not in {SCHEMA_HEAD, None}:
        raise SystemExit(f"schema {version} is not {SCHEMA_HEAD}")
    if snapshots is None:
        raise SystemExit("lab_daily_snapshots missing after restore")
    if published:
        raise SystemExit("published_messages must stay 0")
    print("restore ok; isolated DB only. TELEGRAM SEND COUNT? 0.")


if __name__ == "__main__":
    main()
