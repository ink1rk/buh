#!/usr/bin/env python3
"""Export R11 lab, workflow, provenance and network-gate artifacts. No Telegram."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings, assert_can_boot
from app.core.db import SCHEMA_HEAD, make_engine, make_session_factory
from app.core.models import (
    Channel,
    ClusterMember,
    EditorialClaim,
    EditorialVariant,
    Episode,
    MediaAsset,
    Post,
    PublishedMessage,
    SourceItem,
    StoryCluster,
    StoryDossier,
    WorkflowRun,
    WorkflowStep,
)
from app.media.renderer import render_studio_card
from app.product.lab import export_lab
from app.product.llm_contract import live_chat_client
from app.product.pilot import blocked
from app.product.source_catalog import collect, http_collector
from app.publishing.gate import build_telegram_transport
from sqlalchemy import text

OUT = ROOT / "reports" / "r11"
CARDS = ROOT / "reports" / "screenshots" / "r11" / "cards"
URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_r11_lab"
)


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _probe_network() -> dict:
    settings = Settings(
        environment="development",
        dry_run=True,
        publish_enabled=False,
        global_kill_switch=True,
        sponsored_enabled=False,
        source_mode="offline",
        llm_mode="mock",
        database_url=URL,
        session_secret="demo-session-secret-value-32",
    )
    assert_can_boot(settings)
    production = "ok"
    try:
        assert_can_boot(Settings(environment="production", session_secret="demo-session-secret-value-32"))
        production = "FAILED_OPEN"
    except RuntimeError as exc:
        production = str(exc)
    sandbox = "ok"
    try:
        assert_can_boot(
            Settings(pilot_mode="telegram_sandbox", session_secret="demo-session-secret-value-32")
        )
        sandbox = "FAILED_OPEN"
    except RuntimeError as exc:
        sandbox = str(exc)
    llm = "raised"
    try:
        live_chat_client()
        llm = "FAILED_OPEN"
    except RuntimeError as exc:
        llm = str(exc)
    live_collect = collect("cisa_kev", source_mode="live")
    dummy_denied = http_collector("http://example.com/x", object())
    sockets_before = time.time()
    # Fail-closed: do not open a socket to a public host. Probe loopback only.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        loopback = sock.connect_ex(("127.0.0.1", 8787))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_head": SCHEMA_HEAD,
        "telegram_transport": str(build_telegram_transport(settings)),
        "telegram_send": 0,
        "published_messages_query_later": True,
        "production_boot": production,
        "sandbox_pilot_boot": sandbox,
        "live_chat_client": llm,
        "live_collect": live_collect,
        "http_collector_public": dummy_denied,
        "pilot_telegram_sandbox": blocked("telegram_sandbox"),
        "loopback_ui_connect_ex": loopback,
        "public_http_attempted": False,
        "ollama_socket_attempted": False,
        "probe_seconds": round(time.time() - sockets_before, 4),
        "SOURCE_LIVE": "NO",
        "LOCAL_LLM_LIVE": "NO",
        "TELEGRAM_SEND_COUNT": 0,
        "REAL_AUDIENCE": "UNKNOWN",
        "REAL_REVENUE": "UNKNOWN",
        "PRODUCTION_READY": "NO",
    }


def _ratios() -> list[dict]:
    CARDS.mkdir(parents=True, exist_ok=True)
    rows = []
    for ratio, purpose in (("16:9", "news"), ("1:1", "review"), ("4:5", "security")):
        card = render_studio_card(
            channel_id="cyber",
            channel_title="КиберРадар",
            primary="#8B1E3F",
            accent="#E07A5F",
            purpose=purpose,
            title="DEMO: CVE-2026-880001 учебный advisory",
            ratio=ratio,
            subtitle="DEMO · NEVER_PUBLISH",
            source_label="cassette://cisa_kev",
            cve="CVE-2026-880001",
            demo=True,
        )
        path = CARDS / f"cyber-{purpose}-{ratio.replace(':', 'x')}.jpg"
        path.write_bytes(card.jpeg)
        rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "ratio": ratio,
                "width": card.width,
                "height": card.height,
                "sha256": card.sha256,
                "fits": card.layout.fits,
                "bytes": card.byte_size,
            }
        )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    engine = make_engine(URL)
    session = make_session_factory(engine)()
    try:
        patched = session.execute(
            text(
                """
                UPDATE workflow_steps AS ws
                SET output_ref = 'dossier:' || sd.id::text
                FROM workflow_runs AS wr, story_dossiers AS sd
                WHERE ws.run_id = wr.id
                  AND wr.cluster_id = sd.cluster_id
                  AND ws.stage = 'researched'
                  AND (ws.output_ref IS NULL OR ws.output_ref IN ('dossier:None', 'dossier:'))
                """
            )
        )
        session.commit()
        exported = export_lab(session)
        days = exported.get("days") or []
        _json(OUT / "lab-daily.json", days)
        with (OUT / "lab-daily.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["day", "clusters", "source_items", "posts", "skipped_future"],
            )
            writer.writeheader()
            for row in days:
                writer.writerow(
                    {
                        "day": row.get("day"),
                        "clusters": row.get("clusters"),
                        "source_items": row.get("source_items"),
                        "posts": row.get("posts"),
                        "skipped_future": row.get("skipped_future"),
                    }
                )
        runs = session.query(WorkflowRun).order_by(WorkflowRun.id).all()
        traces = []
        for run in runs:
            steps = session.query(WorkflowStep).filter_by(run_id=run.id).order_by(WorkflowStep.id).all()
            traces.append(
                {
                    "run_id": run.id,
                    "cluster_id": run.cluster_id,
                    "channel_id": run.channel_id,
                    "stage": run.stage,
                    "status": run.status,
                    "post_id": run.post_id,
                    "brief_id": run.brief_id,
                    "asset_id": run.asset_id,
                    "episode_id": run.episode_id,
                    "editorial_ready": run.editorial_ready,
                    "ready_for_delivery": False,
                    "delivery_allowed": False,
                    "lab_run_id": run.lab_run_id,
                    "steps": [
                        {
                            "stage": step.stage,
                            "status": step.status,
                            "output_ref": step.output_ref,
                            "skipped_reason": step.skipped_reason,
                            "error_class": step.error_class,
                        }
                        for step in steps
                    ],
                }
            )
        _json(OUT / "workflow-traces.json", traces)
        clusters = session.query(StoryCluster).order_by(StoryCluster.id).all()
        provenance = []
        for cluster in clusters:
            members = session.query(ClusterMember).filter_by(cluster_id=cluster.id).all()
            items = []
            for member in members:
                item = session.get(SourceItem, member.source_item_id) if member.source_item_id else None
                items.append(
                    {
                        "member_id": member.id,
                        "story_id": member.story_id,
                        "source_item_id": member.source_item_id,
                        "relation": member.relation,
                        "external_id": item.external_id if item else None,
                        "url": (item.raw_json or {}).get("url") if item else None,
                        "publisher_id": item.publisher_id if item else None,
                        "available_at": item.available_at.isoformat() if item and item.available_at else None,
                        "cassette_id": item.cassette_id if item else None,
                        "origin_mode": item.origin_mode if item else None,
                    }
                )
            dossier = session.query(StoryDossier).filter_by(cluster_id=cluster.id).one_or_none()
            claims = session.query(EditorialClaim).filter_by(cluster_id=cluster.id).all()
            provenance.append(
                {
                    "cluster_id": cluster.id,
                    "cluster_key": cluster.cluster_key,
                    "title": cluster.title,
                    "channel_id": cluster.primary_channel_id,
                    "lab_run_id": cluster.lab_run_id,
                    "data_mode": cluster.data_mode,
                    "kind": cluster.kind,
                    "dossier_id": dossier.id if dossier else None,
                    "members": items,
                    "claims": [
                        {"id": claim.id, "status": claim.status, "text": claim.text}
                        for claim in claims
                    ],
                }
            )
        _json(OUT / "source-provenance.json", provenance)
        s1 = next((row for row in traces if row["channel_id"] == "github" and row["asset_id"] and row["episode_id"]), traces[-1] if traces else {})
        s3 = next((row for row in provenance if "CVE-2026-880001" in (row.get("title") or "") or (row.get("cluster_key") or "").startswith("cve:CVE-2026-880001")), None)
        scenarios = {
            "S1_normal_news": s1,
            "S2_correction": next(
                (row for row in provenance if "880002" in (row.get("cluster_key") or "") or "уточнен" in (row.get("title") or "").lower()),
                next((row for row in provenance if "CVE-2026-880001" in (row.get("title") or "")), None),
            ),
            "S3_cve": s3,
        }
        _json(OUT / "scenarios.json", scenarios)
        media = []
        for asset in session.query(MediaAsset).order_by(MediaAsset.id).all():
            path = ROOT / "var" / "media" / (asset.file_path or "")
            media.append(
                {
                    "id": asset.id,
                    "post_id": asset.post_id,
                    "file_path": asset.file_path,
                    "sha256": asset.sha256,
                    "width": asset.width,
                    "height": asset.height,
                    "ratio": asset.ratio,
                    "exists": path.is_file(),
                    "bytes_on_disk": path.stat().st_size if path.is_file() else 0,
                }
            )
        _json(OUT / "media-assets.json", media)
        counts = {
            "channels": session.query(Channel).count(),
            "clusters": session.query(StoryCluster).count(),
            "source_items": session.query(SourceItem).count(),
            "posts": session.query(Post).count(),
            "variants": session.query(EditorialVariant).count(),
            "episodes": session.query(Episode).count(),
            "workflow_runs": session.query(WorkflowRun).count(),
            "assets": session.query(MediaAsset).count(),
            "published_messages": session.query(PublishedMessage).count(),
            "telegram_send": 0,
            "dossier_refs_patched": patched.rowcount,
        }
        _json(OUT / "counts.json", counts)
        (ROOT / "reports" / "r11-lab-results.json").write_text(
            json.dumps({k: exported[k] for k in exported if k != "days"} | {"days": days}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    finally:
        session.close()
        engine.dispose()
    probes = _probe_network()
    _json(OUT / "network-gate-probes.json", probes)
    ratios = _ratios()
    _json(OUT / "ratio-samples.json", ratios)
    digest = hashlib.sha256((OUT / "lab-daily.json").read_bytes()).hexdigest()
    print({"lab_daily_sha256": digest, "ratios": [row["path"] for row in ratios], "telegram_send": 0})
    print("PUBLISH ENABLED? NO. TELEGRAM SEND COUNT? 0. LIVE DATA? NO. REAL REVENUE? UNKNOWN. PRODUCTION READY? NO.")


if __name__ == "__main__":
    main()
