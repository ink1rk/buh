"""Local editorial workflow. It never sends Telegram and never sets delivery_allowed."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import EditorialTask, Post, Story, StoryCluster, WorkflowRun, WorkflowStep
from app.core.timeutil import ensure_utc, utcnow
from app.product.dossier import build_dossier
from app.product.drafts import create_angles
from app.product.editorial import quality_gate

STAGES = (
    "ingest",
    "normalize",
    "deduplicate",
    "rank",
    "dossier",
    "brief",
    "variants",
    "qa",
    "render",
    "propose_slot",
    "request_approval",
    "await_human",
)
MAX_ATTEMPTS = 3
MAX_RUNNING = 8


def start_run(
    session: Session,
    *,
    cluster: StoryCluster,
    channel_id: str,
    actor: str,
    now: datetime | None = None,
    lab_run_id: int | None = None,
) -> WorkflowRun:
    moment = ensure_utc(now or utcnow())
    key = hashlib.sha256(f"wf:{cluster.id}:{channel_id}".encode()).hexdigest()[:40]
    existing = session.query(WorkflowRun).filter_by(idempotency_key=key).one_or_none()
    if existing is not None:
        return existing
    running = session.query(WorkflowRun).filter_by(status="running", paused=False).count()
    run = WorkflowRun(
        cluster_id=cluster.id,
        channel_id=channel_id,
        trace_id=secrets.token_hex(8),
        idempotency_key=key,
        stage="ingest",
        status="queued" if running >= MAX_RUNNING else "running",
        attempt=1,
        editorial_ready=False,
        delivery_allowed=False,
        created_at=moment,
        updated_at=moment,
        lab_run_id=lab_run_id,
    )
    session.add(run)
    session.flush()
    add_audit(session, actor=actor, action="workflow_start", entity="workflow", entity_id=run.id, result=run.status)
    return run


def tick_run(session: Session, run: WorkflowRun, now: datetime | None = None) -> WorkflowRun:
    moment = ensure_utc(now or utcnow())
    if run.paused or run.status in {"done", "dead", "cancelled"}:
        return run
    if run.status == "queued":
        running = session.query(WorkflowRun).filter_by(status="running", paused=False).count()
        if running >= MAX_RUNNING:
            return run
        run.status = "running"
    cluster = session.get(StoryCluster, run.cluster_id) if run.cluster_id else None
    if cluster is None:
        return _fail(run, "cluster missing", moment)
    started = utcnow()
    try:
        _advance(session, run, cluster, moment)
        duration = int((utcnow() - started).total_seconds() * 1000)
        session.add(
            WorkflowStep(
                run_id=run.id,
                stage=run.stage,
                status="ok",
                attempt=run.attempt,
                duration_ms=duration,
                updated_at=moment,
            )
        )
    except Exception as exc:  # noqa: BLE001 — local jobs must not look successful on timeout/error
        run.attempt += 1
        run.last_error = str(exc)[:500]
        run.retry_after = moment + timedelta(seconds=min(60, 2**run.attempt))
        session.add(
            WorkflowStep(
                run_id=run.id,
                stage=run.stage,
                status="error",
                attempt=run.attempt,
                last_error=run.last_error,
                updated_at=moment,
            )
        )
        if run.attempt > MAX_ATTEMPTS:
            run.status = "dead"
        else:
            run.status = "retry"
    run.updated_at = moment
    run.delivery_allowed = False
    return run


def pause_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.paused = True
    run.status = "paused"
    add_audit(session, actor=actor, action="workflow_pause", entity="workflow", entity_id=run.id, result="paused")
    return run


def resume_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.paused = False
    run.status = "running" if run.status != "dead" else run.status
    add_audit(session, actor=actor, action="workflow_resume", entity="workflow", entity_id=run.id, result=run.status)
    return run


def retry_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    if run.status not in {"dead", "retry", "error"}:
        return run
    run.attempt = 1
    run.status = "running"
    run.paused = False
    run.last_error = ""
    add_audit(session, actor=actor, action="workflow_retry", entity="workflow", entity_id=run.id, result="running")
    return run


def cancel_run(session: Session, run: WorkflowRun, actor: str) -> WorkflowRun:
    run.status = "cancelled"
    run.paused = True
    add_audit(session, actor=actor, action="workflow_cancel", entity="workflow", entity_id=run.id, result="cancelled")
    return run


def run_until_human(session: Session, run: WorkflowRun, now: datetime | None = None) -> WorkflowRun:
    guard = 0
    while run.status in {"running", "queued", "retry"} and run.stage != "await_human" and guard < 20:
        tick_run(session, run, now)
        guard += 1
    return run


def board(session: Session) -> dict:
    rows = []
    for run in session.query(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(80):
        rows.append(
            {
                "id": run.id,
                "cluster_id": run.cluster_id,
                "channel_id": run.channel_id,
                "stage": run.stage,
                "status": run.status,
                "attempt": run.attempt,
                "last_error": run.last_error,
                "paused": run.paused,
                "editorial_ready": run.editorial_ready,
                "delivery_allowed": run.delivery_allowed,
                "policy_block": "отправка в Telegram заблокирована политикой",
            }
        )
    tasks = session.query(EditorialTask).filter_by(status="open").order_by(EditorialTask.id.desc()).limit(40).all()
    return {"runs": rows, "tasks": tasks, "telegram": "blocked_by_policy"}


def _advance(session: Session, run: WorkflowRun, cluster: StoryCluster, now: datetime) -> None:
    index = STAGES.index(run.stage) if run.stage in STAGES else 0
    stage = STAGES[index]
    if stage == "ingest":
        run.stage = "normalize"
        return
    if stage == "normalize":
        run.stage = "deduplicate"
        return
    if stage == "deduplicate":
        run.stage = "rank"
        return
    if stage == "rank":
        run.stage = "dossier"
        return
    if stage == "dossier":
        build_dossier(session, cluster, now)
        run.stage = "brief"
        return
    if stage == "brief":
        run.stage = "variants"
        return
    if stage == "variants":
        post = _post_for(session, cluster, run.channel_id)
        if post is not None:
            create_angles(session, post, actor="workflow")
        run.stage = "qa"
        return
    if stage == "qa":
        post = _post_for(session, cluster, run.channel_id)
        if post is not None:
            post.quality_json = quality_gate(session, post, session.get(Story, post.story_id))
        run.stage = "render"
        return
    if stage == "render":
        run.stage = "propose_slot"
        return
    if stage == "propose_slot":
        run.stage = "request_approval"
        return
    if stage == "request_approval":
        run.editorial_ready = True
        run.delivery_allowed = False
        run.stage = "await_human"
        run.status = "await_human"
        return
    run.stage = "await_human"
    run.status = "await_human"


def _post_for(session: Session, cluster: StoryCluster, channel_id: str) -> Post | None:
    from app.core.models import ClusterMember

    member = (
        session.query(ClusterMember)
        .filter_by(cluster_id=cluster.id, relation="member")
        .filter(ClusterMember.story_id.is_not(None))
        .order_by(ClusterMember.id)
        .first()
    )
    if member is None or member.story_id is None:
        return session.query(Post).filter_by(channel_id=channel_id).order_by(Post.id.desc()).first()
    return session.query(Post).filter_by(story_id=member.story_id, channel_id=channel_id).first()


def _fail(run: WorkflowRun, message: str, now: datetime) -> WorkflowRun:
    run.last_error = message
    run.status = "dead"
    run.updated_at = now
    run.delivery_allowed = False
    return run
