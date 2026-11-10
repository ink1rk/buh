"""Editorial DAG. Each stage writes an artifact or an honest skip. Telegram is never sent."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.config import ROOT
from app.core.models import (
    Channel,
    ClusterMember,
    EditorialBrief,
    EditorialTask,
    EditorialVariant,
    Episode,
    MediaAsset,
    Post,
    StoryCluster,
    StoryDossier,
    WorkflowRun,
    WorkflowStep,
)
from app.core.timeutil import ensure_utc
from app.media.renderer import render_studio_card
from app.product.dossier import build_dossier
from app.product.drafts import create_angles, ensure_post_for_cluster
from app.product.editorial import quality_gate
from app.product.intelligence import record_score_revision, score_cluster
from app.product.programs import SERIES, _msk_slot, ensure_series
from app.product.radar import rank_open_clusters

STAGES = (
    "source_received",
    "normalized",
    "clustered",
    "ranked",
    "researched",
    "brief_ready",
    "variants_ready",
    "fact_checked",
    "asset_rendered",
    "slot_proposed",
    "approval_requested",
    "approved_or_rejected",
)
HUMAN_WAIT = {"await_human", "needs_input", "blocked", "approved_or_rejected"}
THEMES = {
    "ai_news": ("#6750A4", "#00CDB6"),
    "ai_tools": ("#185ADB", "#4DE1C1"),
    "github": ("#24292F", "#58A6FF"),
    "cyber": ("#8B1E3F", "#E07A5F"),
    "infra": ("#1B4332", "#52B788"),
    "homelab": ("#3D405B", "#F2CC8F"),
    "dev": ("#1D3557", "#A8DADC"),
    "future": ("#22223B", "#C9ADA7"),
}


def start_run(
    session: Session,
    *,
    cluster: StoryCluster,
    channel_id: str,
    actor: str,
    now: datetime | None = None,
    lab_run_id: int | None = None,
) -> WorkflowRun:
    del now
    key = f"wf:{cluster.id}:{channel_id}"
    existing = session.query(WorkflowRun).filter_by(idempotency_key=key).one_or_none()
    if existing is not None:
        return existing
    run = WorkflowRun(
        cluster_id=cluster.id,
        channel_id=channel_id,
        stage="source_received",
        status="running",
        idempotency_key=key,
        trace_id=key,
        delivery_allowed=False,
        ready_for_delivery=False,
        lab_run_id=lab_run_id if lab_run_id is not None else cluster.lab_run_id,
    )
    session.add(run)
    session.flush()
    add_audit(session, actor=actor, action="workflow.start", entity="workflow_run", entity_id=run.id, result="started", payload={"stage": run.stage})
    return run


def run_until_human(session: Session, run: WorkflowRun, now: datetime) -> WorkflowRun:
    guard = 0
    while run.status in {"running", "queued", "retry"} and run.stage not in HUMAN_WAIT and not run.paused and guard < 24:
        _advance(session, run, now)
        guard += 1
        session.flush()
    run.delivery_allowed = False
    run.ready_for_delivery = False
    session.flush()
    return run


def pause_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.paused = True
    run.status = "paused"
    add_audit(session, actor=actor, action="workflow.pause", entity="workflow_run", entity_id=run.id, result="paused")
    session.flush()
    return run


def resume_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.paused = False
    if run.status == "paused":
        run.status = "running"
    add_audit(session, actor=actor, action="workflow.resume", entity="workflow_run", entity_id=run.id, result="resumed")
    session.flush()
    return run


def retry_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.attempt += 1
    run.status = "running"
    run.paused = False
    run.last_error = ""
    add_audit(session, actor=actor, action="workflow.retry", entity="workflow_run", entity_id=run.id, result="retry", payload={"attempt": run.attempt})
    session.flush()
    return run


def approve_run(session: Session, run: WorkflowRun, actor: str, *, accepted: bool = True) -> WorkflowRun:
    run.stage = "approved_or_rejected"
    run.status = "done" if accepted else "rejected"
    run.ready_for_human = False
    run.editorial_ready = accepted and _editorial_ready(session, run)
    run.delivery_allowed = False
    run.ready_for_delivery = False
    _step(session, run, "approved_or_rejected", "done" if accepted else "rejected", output_ref=f"actor:{actor}")
    add_audit(session, actor=actor, action="workflow.decide", entity="workflow_run", entity_id=run.id, result="accepted" if accepted else "rejected")
    session.flush()
    return run


def board(session: Session) -> dict:
    runs = session.query(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(40).all()
    tasks = session.query(EditorialTask).filter_by(status="open").order_by(EditorialTask.id.desc()).limit(20).all()
    return {"runs": runs, "tasks": tasks, "delivery_allowed": False}


def lineage(session: Session, run: WorkflowRun) -> dict:
    steps = session.query(WorkflowStep).filter_by(run_id=run.id).order_by(WorkflowStep.id).all()
    return {
        "run_id": run.id,
        "cluster_id": run.cluster_id,
        "channel_id": run.channel_id,
        "stage": run.stage,
        "editorial_ready": run.editorial_ready,
        "delivery_allowed": False,
        "ready_for_delivery": False,
        "post_id": run.post_id,
        "brief_id": run.brief_id,
        "asset_id": run.asset_id,
        "episode_id": run.episode_id,
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


def _advance(session: Session, run: WorkflowRun, now: datetime) -> None:
    cluster = session.get(StoryCluster, run.cluster_id) if run.cluster_id else None
    if cluster is None:
        _fail(session, run, "needs_input", "cluster_missing")
        return
    handlers = {
        "source_received": _stage_source,
        "normalized": _stage_normalized,
        "clustered": _stage_clustered,
        "ranked": _stage_ranked,
        "researched": _stage_researched,
        "brief_ready": _stage_brief,
        "variants_ready": _stage_variants,
        "fact_checked": _stage_facts,
        "asset_rendered": _stage_asset,
        "slot_proposed": _stage_slot,
        "approval_requested": _stage_approval,
    }
    handler = handlers.get(run.stage)
    if handler is None:
        run.stage = "source_received"
        return
    handler(session, run, cluster, now)


def _stage_source(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    members = session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").count()
    if members == 0:
        _needs_input(session, run, cluster, "у кластера нет исходных записей")
        return
    _finish_stage(session, run, "source_received", f"cluster:{cluster.id}:members:{members}", next_stage="normalized")


def _stage_normalized(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    if not cluster.cluster_key:
        _fail(session, run, "blocked", "missing_cluster_key")
        return
    _finish_stage(session, run, "normalized", f"key:{cluster.cluster_key}", next_stage="clustered")


def _stage_clustered(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    _finish_stage(session, run, "clustered", f"cluster:{cluster.id}", next_stage="ranked")


def _stage_ranked(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    rank_open_clusters(session, now)
    dims, _penalties, total, _why, _ev, _conf = score_cluster(
        cluster,
        run.channel_id,
        samples=1,
        members=1,
        source_ids=[],
        now=now,
        anchor=cluster.first_seen or now,
        preprint=False,
        license_state="unknown",
        channel_hot=1,
    )
    record_score_revision(session, cluster, run.channel_id, dimensions=dims, total=total)
    session.flush()
    _finish_stage(session, run, "ranked", f"cluster:{cluster.id}:score:{total}", next_stage="researched")


def _stage_researched(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    existing = session.query(StoryDossier).filter_by(cluster_id=cluster.id).one_or_none()
    if existing is not None:
        session.flush()
        if existing.id is None:
            _fail(session, run, "blocked", "dossier_missing_id")
            return
        _finish_stage(
            session,
            run,
            "researched",
            f"dossier:{existing.id}",
            next_stage="brief_ready",
            skipped="already_satisfied",
        )
        return
    dossier = build_dossier(session, cluster, now)
    session.flush()
    if dossier.id is None:
        _fail(session, run, "blocked", "dossier_missing_id")
        return
    _finish_stage(session, run, "researched", f"dossier:{dossier.id}", next_stage="brief_ready")


def _stage_brief(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    post = _bind_post(session, run, cluster)
    if post is None:
        return
    brief = session.query(EditorialBrief).filter_by(cluster_id=cluster.id, channel_id=run.channel_id).order_by(EditorialBrief.id.desc()).first()
    if brief is None:
        brief = EditorialBrief(
            cluster_id=cluster.id,
            channel_id=run.channel_id,
            angle_id=post.angle_id or "news",
            format_id=post.format_id,
            notes="workflow brief",
            actor="workflow",
            lab_run_id=run.lab_run_id,
        )
        session.add(brief)
        session.flush()
        skipped = ""
    else:
        skipped = "already_satisfied"
    run.brief_id = brief.id
    post.brief_id = brief.id
    _finish_stage(session, run, "brief_ready", f"brief:{brief.id}", next_stage="variants_ready", skipped=skipped)


def _stage_variants(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    post = _bind_post(session, run, cluster)
    if post is None:
        return
    existing = session.query(EditorialVariant).filter_by(post_id=post.id).count()
    if existing >= 2:
        _finish_stage(
            session,
            run,
            "variants_ready",
            f"post:{post.id}:variants:{existing}",
            next_stage="fact_checked",
            skipped="already_satisfied",
        )
        return
    created = create_angles(session, post, actor="workflow")
    _finish_stage(session, run, "variants_ready", f"post:{post.id}:variants:{len(created)}", next_stage="fact_checked")


def _stage_facts(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    post = _bind_post(session, run, cluster)
    if post is None:
        return
    from app.core.models import Story

    story = session.get(Story, post.story_id)
    gate = quality_gate(session, post, story) if story is not None else {"ok": False}
    post.quality_json = gate
    _finish_stage(session, run, "fact_checked", f"post:{post.id}:quality", next_stage="asset_rendered")


def _stage_asset(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    post = _bind_post(session, run, cluster)
    if post is None:
        return
    existing = (
        session.query(MediaAsset)
        .filter_by(post_id=post.id, kind="card", content_hash=post.final_hash)
        .order_by(MediaAsset.id.desc())
        .first()
    )
    if existing is not None:
        run.asset_id = existing.id
        _finish_stage(
            session,
            run,
            "asset_rendered",
            f"asset:{existing.id}",
            next_stage="slot_proposed",
            skipped="already_satisfied",
        )
        return
    channel = session.get(Channel, run.channel_id)
    primary, accent = THEMES.get(run.channel_id, ("#1c2434", "#d4a054"))
    card = render_studio_card(
        channel_id=run.channel_id,
        channel_title=channel.title if channel else run.channel_id,
        primary=primary,
        accent=accent,
        purpose="news",
        title=post.title,
        ratio="16:9",
        subtitle="DEMO · NEVER_PUBLISH",
        source_label="учебный источник",
        demo=True,
    )
    if not card.layout.fits:
        _step(
            session,
            run,
            "asset_rendered",
            "blocked",
            error_class="overflow",
            skipped=card.layout.overflow or "title_overflow",
        )
        run.stage = "blocked"
        run.status = "blocked"
        run.last_error = "card overflow"
        return
    directory = ROOT / "var" / "media"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"wf-{run.id}-post-{post.id}.jpg"
    (directory / filename).write_bytes(card.jpeg)
    asset = MediaAsset(
        post_id=post.id,
        kind="card",
        file_path=filename,
        rights_basis=card.rights_basis,
        sha256=card.sha256,
        width=card.width,
        height=card.height,
        byte_size=card.byte_size,
        status="ready",
        render_version="studio-v3",
        draft_version=post.draft_version,
        content_hash=post.final_hash,
        template_version="studio-v3",
        ratio="16:9",
        qa_status="ok",
        source_license="own_typographic_template",
        generator_mode="local_template",
        alt_text=post.title[:180],
        purpose="news",
        lab_run_id=run.lab_run_id,
    )
    session.add(asset)
    session.flush()
    run.asset_id = asset.id
    _finish_stage(session, run, "asset_rendered", f"asset:{asset.id}", next_stage="slot_proposed")


def _stage_slot(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    post = _bind_post(session, run, cluster)
    if post is None:
        return
    existing = session.query(Episode).filter_by(draft_post_id=post.id).order_by(Episode.id.desc()).first()
    if existing is not None:
        run.episode_id = existing.id
        _finish_stage(
            session,
            run,
            "slot_proposed",
            f"episode:{existing.id}",
            next_stage="approval_requested",
            skipped="already_satisfied",
        )
        return
    ensure_series(session)
    session.flush()
    channel = session.get(Channel, run.channel_id)
    slot_label = str((channel.schedule_json or ["12:00"])[0]) if channel else "12:00"
    when = _msk_slot(ensure_utc(now).date() + timedelta(days=1), slot_label)
    occupied = session.query(Episode).filter_by(channel_id=run.channel_id, slot_utc=when).first()
    if occupied is not None:
        task = EditorialTask(
            kind="vacancy",
            cluster_id=cluster.id,
            channel_id=run.channel_id,
            title=f"слот {when.isoformat()} занят",
            reason="слот пуст: нет свободного окна под этот сюжет",
            status="open",
            lab_run_id=run.lab_run_id,
            post_id=post.id,
            priority="normal",
        )
        session.add(task)
        session.flush()
        _finish_stage(
            session,
            run,
            "slot_proposed",
            f"task:{task.id}",
            next_stage="approval_requested",
            skipped="no_free_slot",
        )
        return
    series_id = next((spec["id"] for spec in SERIES if run.channel_id in spec["allowed_channels"]), SERIES[0]["id"])
    episode = Episode(
        series_id=series_id,
        channel_id=run.channel_id,
        slot_utc=when,
        status="proposed",
        calendar_status="proposed",
        draft_post_id=post.id,
        reason="workflow propose",
        origin="workflow",
        program_kind="breaking",
        lab_run_id=run.lab_run_id,
        item_refs=[cluster.id],
    )
    session.add(episode)
    session.flush()
    run.episode_id = episode.id
    _finish_stage(session, run, "slot_proposed", f"episode:{episode.id}", next_stage="approval_requested")


def _stage_approval(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    task = EditorialTask(
        kind="approval",
        cluster_id=cluster.id,
        channel_id=run.channel_id,
        title="Нужно решение редактора",
        reason="editorial_ready ждёт человека; доставка запрещена политикой",
        status="open",
        lab_run_id=run.lab_run_id,
        post_id=run.post_id,
        priority="high",
        due_at=ensure_utc(now) + timedelta(hours=12),
    )
    session.add(task)
    session.flush()
    run.ready_for_human = True
    run.editorial_ready = _editorial_ready(session, run)
    run.delivery_allowed = False
    run.ready_for_delivery = False
    run.status = "waiting_human"
    _finish_stage(session, run, "approval_requested", f"task:{task.id}", next_stage="approval_requested")


def _bind_post(session: Session, run: WorkflowRun, cluster: StoryCluster) -> Post | None:
    if run.post_id:
        post = session.get(Post, run.post_id)
        if post is not None:
            return post
    post = ensure_post_for_cluster(session, cluster, run.channel_id)
    if post is None:
        _needs_input(session, run, cluster, "у кластера нет своей истории для черновика")
        return None
    run.post_id = post.id
    return post


def _editorial_ready(session: Session, run: WorkflowRun) -> bool:
    if not run.post_id or not run.brief_id or not run.asset_id:
        return False
    variants = session.query(EditorialVariant).filter_by(post_id=run.post_id).count()
    return variants >= 2


def _finish_stage(
    session: Session,
    run: WorkflowRun,
    stage: str,
    output_ref: str,
    *,
    next_stage: str,
    skipped: str = "",
) -> None:
    status = "skipped" if skipped else "done"
    _step(session, run, stage, status, output_ref=output_ref, skipped=skipped)
    run.stage = next_stage
    run.lineage_json = {**(run.lineage_json or {}), stage: output_ref}
    if next_stage == stage == "approval_requested":
        run.stage = "approval_requested"


def _step(
    session: Session,
    run: WorkflowRun,
    stage: str,
    status: str,
    *,
    output_ref: str = "",
    skipped: str = "",
    error_class: str = "",
) -> WorkflowStep:
    digest = hashlib.sha256(f"{run.id}:{stage}:{output_ref}".encode()).hexdigest()
    row = WorkflowStep(
        run_id=run.id,
        stage=stage,
        status=status,
        attempt=run.attempt,
        input_hash=digest,
        output_ref=output_ref,
        skipped_reason=skipped,
        error_class=error_class,
    )
    session.add(row)
    session.flush()
    return row


def _needs_input(session: Session, run: WorkflowRun, cluster: StoryCluster, reason: str) -> None:
    task = EditorialTask(
        kind="needs_input",
        cluster_id=cluster.id,
        channel_id=run.channel_id,
        title="Нужны исходные данные",
        reason=reason,
        status="open",
        lab_run_id=run.lab_run_id,
        priority="high",
    )
    session.add(task)
    session.flush()
    run.stage = "needs_input"
    run.status = "needs_input"
    run.last_error = reason
    _step(session, run, "needs_input", "needs_input", output_ref=f"task:{task.id}", skipped=reason, error_class="needs_input")


def _fail(session: Session, run: WorkflowRun, status: str, error_class: str) -> None:
    run.stage = status
    run.status = status
    run.last_error = error_class
    _step(session, run, run.stage, status, error_class=error_class)
