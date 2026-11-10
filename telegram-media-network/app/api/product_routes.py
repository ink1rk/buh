"""Product API. Every mutating call needs a session, CSRF, and a role. Nothing here sends Telegram."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles, require_user
from app.core.audit import add_audit
from app.core.models import (
    AdCampaign,
    Channel,
    ClusterMember,
    Episode,
    EvidenceSnapshot,
    FinanceEvent,
    MediaAsset,
    Post,
    PostVersion,
    RankedCandidate,
    Series,
    StoryCluster,
)
from app.core.timeutil import ensure_utc, utcnow
from app.media.renderer import choose_rights, render_network_card
from app.product.commercial import forecast, media_kit, seed_commercial
from app.product.demo_pack import build_pack
from app.product.drafts import fallback_from_invalid, materialise_desk, variants_for
from app.product.editorial import ensure_profiles, quality_gate
from app.product.growth import board as growth_board
from app.product.growth import ensure_metrics, seed_experiments, snapshot_derived
from app.product.insights import funnel, record_manual, seed_demo_campaigns
from app.product.planning import lock_episode
from app.product.programs import move_episode, propose_fortnight
from app.product.radar import bulk_list, import_observations, merge_into, route_cluster, split_member

router = APIRouter()


class RouteBody(BaseModel):
    channel_id: str
    reason: str = ""
    expected_version: int = 0


class BulkBody(BaseModel):
    cluster_ids: list[int] = Field(default_factory=list)
    list_name: str
    reason: str = ""


class VariantBody(BaseModel):
    style: str = "news"
    model_mode: str = "mock"
    expected_version: int = 1
    invalid_payload: bool = False


class RenderBody(BaseModel):
    template_id: str = "hero"
    rights_basis: str = "own_typographic_template"
    allow_remote: bool = False


class MoveBody(BaseModel):
    slot_utc: datetime
    expected_version: int


class MeasureBody(BaseModel):
    channel_id: str
    kind: str
    value: int | None = None


class CampaignBody(BaseModel):
    advertiser: str
    channel_id: str
    demo: bool = True


def _envelope(data: dict, mode: str = "measured") -> dict:
    return {"data_mode": mode, "as_of": utcnow().isoformat(), "sources": ["postgres"], **data}


@router.get("/api/v1/radar/clusters")
def radar_clusters(
    channel_id: str = "",
    status: str = "",
    q: str = "",
    page: int = 1,
    auth=Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    del auth
    query = db.query(StoryCluster)
    if channel_id:
        query = query.filter(StoryCluster.primary_channel_id == channel_id)
    if status:
        query = query.filter(StoryCluster.list_name == status)
    if q:
        query = query.filter(StoryCluster.title.ilike(f"%{q[:80]}%"))
    page = max(1, page)
    rows = query.order_by(StoryCluster.id).offset((page - 1) * 20).limit(20).all()
    payload = []
    for cluster in rows:
        rank = (
            db.query(RankedCandidate)
            .filter_by(cluster_id=cluster.id, channel_id=cluster.primary_channel_id)
            .order_by(RankedCandidate.id.desc())
            .first()
        )
        members = db.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").count()
        payload.append(
            {
                "id": cluster.id,
                "title": cluster.title,
                "channel_id": cluster.primary_channel_id,
                "list_name": cluster.list_name,
                "members": members,
                "score": None if rank is None else rank.rank_score,
                "explanation": "" if rank is None else rank.explanation,
                "dimensions": {} if rank is None else rank.dimensions_json,
            }
        )
    mode = "measured"
    if payload and "DEMO" in str(payload[0]["title"] or ""):
        mode = "demo"
    return _envelope({"page": page, "clusters": payload}, mode)


@router.post("/api/v1/radar/clusters/{cluster_id}/route")
def radar_route(
    cluster_id: int,
    body: RouteBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    cluster = db.get(StoryCluster, cluster_id)
    if cluster is None or db.get(Channel, body.channel_id) is None:
        raise HTTPException(status_code=404, detail="cluster or channel missing")
    if not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason required")
    route_cluster(db, cluster, body.channel_id, body.reason, user.username)
    db.commit()
    return _envelope({"id": cluster.id, "channel_id": cluster.primary_channel_id})


@router.post("/api/v1/radar/clusters/bulk")
def radar_bulk(
    body: BulkBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        changed = bulk_list(db, body.cluster_ids, body.list_name, body.reason or "ручная пометка", user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _envelope({"changed": changed})


@router.post("/api/v1/demo/load")
def demo_load(user=Depends(require_roles("OWNER")), db: Session = Depends(get_db)) -> dict:
    moment = utcnow()
    stats = import_observations(db, build_pack(), moment)
    ensure_profiles(db)
    posts = materialise_desk(db)
    calendar = propose_fortnight(db, moment)
    campaigns = seed_demo_campaigns(db, moment)
    commercial = seed_commercial(db, moment)
    ensure_metrics(db)
    experiments = seed_experiments(db)
    metrics = snapshot_derived(db, moment, demo=True)
    add_audit(db, actor=user.username, action="demo_load", entity="network", result="loaded")
    db.commit()
    return _envelope(
        {
            **stats,
            "posts": posts,
            "episodes": calendar["created"],
            "skipped": len(calendar["skipped"]),
            "campaigns": campaigns,
            "commercial": commercial,
            "horizon_days": calendar.get("horizon_days", 28),
            "experiments": experiments,
            "metrics": metrics,
        },
        "demo",
    )


class MergeBody(BaseModel):
    target_id: int
    reason: str


class SplitBody(BaseModel):
    member_id: int
    reason: str


@router.post("/api/v1/radar/clusters/{cluster_id}/merge")
def radar_merge(
    cluster_id: int,
    body: MergeBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        merge_into(db, cluster_id, body.target_id, user.username, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _envelope({"merged": cluster_id, "into": body.target_id})


@router.post("/api/v1/radar/clusters/{cluster_id}/split")
def radar_split(
    cluster_id: int,
    body: SplitBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        created = split_member(db, cluster_id, body.member_id, user.username, body.reason)
    except ValueError as extra:
        raise HTTPException(status_code=422, detail=str(extra)) from extra
    db.commit()
    return _envelope({"id": created.id, "split_from": cluster_id})


@router.get("/api/v1/posts/{post_id}/quality")
def post_quality(post_id: int, auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="post missing")
    from app.core.models import Story

    return _envelope(quality_gate(db, post, db.get(Story, post.story_id)))


@router.get("/api/v1/commercial/mediakit")
def commercial_mediakit(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return _envelope(media_kit(db), "demo")


@router.get("/api/v1/commercial/forecast")
def commercial_forecast(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return _envelope(forecast(db), "demo")


@router.get("/api/v1/growth")
def growth_metrics(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return _envelope(growth_board(db), "mixed")


class LockBody(BaseModel):
    reason: str = ""


@router.post("/api/v1/calendar/episodes/{episode_id}/lock")
def calendar_lock(
    episode_id: int,
    body: LockBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    del body
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode missing")
    lock_episode(db, episode, user.username)
    return _envelope({"id": episode.id, "locked": True, "version": episode.version})


@router.get("/api/v1/posts/{post_id}/evidence")
def post_evidence(post_id: int, auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    rows = db.query(EvidenceSnapshot).filter_by(post_id=post_id).order_by(EvidenceSnapshot.id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="no evidence")
    return _envelope(
        {
            "claims": [
                {
                    "claim_id": row.claim_id,
                    "text": row.claim_text,
                    "source_url": row.source_url,
                    "status": "extracted",
                    "verified_at": None,
                    "origin_kind": row.origin_kind,
                }
                for row in rows
            ]
        }
    )


@router.post("/api/v1/posts/{post_id}/draft-variants")
def draft_variants(
    post_id: int,
    body: VariantBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="post missing")
    if body.invalid_payload or body.model_mode == "invalid":
        variant = fallback_from_invalid(post.channel_id, post.title)
    else:
        found = [item for item in variants_for(db, post) if item["angle"] == body.style]
        variant = found[0] if found else variants_for(db, post)[0]
    add_audit(db, actor=user.username, action="draft_variant", entity="post", entity_id=post.id, result="review")
    db.commit()
    return _envelope({"variant": variant, "outbox": 0, "requires_review": True}, "demo" if post.synthetic else "measured")


@router.get("/api/v1/posts/{post_id}/history")
def post_history(post_id: int, auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    rows = db.query(PostVersion).filter_by(post_id=post_id).order_by(PostVersion.version).all()
    return _envelope(
        {
            "versions": [
                {"version": row.version, "title": row.title, "body": row.body, "hash": row.final_hash} for row in rows
            ]
        }
    )


@router.get("/api/v1/studio/templates")
def studio_templates(auth=Depends(require_user)) -> dict:
    del auth
    return _envelope(
        {
            "templates": [
                {"id": "hero", "title": "News/Hero"},
                {"id": "tool", "title": "Tool Spotlight"},
                {"id": "advisory", "title": "Security Advisory"},
                {"id": "digest", "title": "Daily/Weekly Digest"},
            ]
        }
    )


@router.post("/api/v1/posts/{post_id}/render")
def render_post(
    post_id: int,
    body: RenderBody,
    request: Request,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    del user
    post = db.get(Post, post_id)
    channel = db.get(Channel, post.channel_id) if post else None
    if post is None or channel is None:
        raise HTTPException(status_code=404, detail="post missing")
    theme = channel.theme_json or {}
    template_id = body.template_id if body.template_id in {"lead", "hero", "tool", "security", "advisory", "digest", "deep-dive"} else "lead"
    card = render_network_card(
        channel_id=channel.id,
        channel_title=channel.title,
        primary=str(theme.get("primary") or "#1c2434"),
        accent=str(theme.get("accent") or "#d7e2ea"),
        template_id=template_id,
        title=post.title,
        subtitle="DEMO" if post.synthetic else "",
        source_label=(post.source_links_json or [""])[0][:80],
        cve=next((token.strip(":,.") for token in post.title.split() if token.startswith("CVE-")), ""),
        demo=post.synthetic,
    )
    remote = b"remote-bytes" if body.rights_basis != "own_typographic_template" else None
    chosen, basis = choose_rights(remote, body.rights_basis, body.allow_remote, card)
    directory = request.app.state.settings.media_dir
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"post-{post.id}-v{post.draft_version}.jpg"
    (directory / filename).write_bytes(chosen.jpeg)
    db.add(
        MediaAsset(
            post_id=post.id,
            kind="card",
            file_path=filename,
            rights_basis=basis,
            sha256=chosen.sha256,
            width=chosen.width,
            height=chosen.height,
            byte_size=chosen.byte_size,
            status="ready",
            render_version=f"studio-{template_id}",
            draft_version=post.draft_version,
            content_hash=post.final_hash,
        )
    )
    db.commit()
    return _envelope({"rights_basis": basis, "sha256": chosen.sha256, "width": chosen.width, "height": chosen.height})


@router.get("/api/v1/calendar")
def calendar_api(channel_id: str = "", auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    query = db.query(Episode)
    if channel_id:
        query = query.filter(Episode.channel_id == channel_id)
    rows = query.order_by(Episode.slot_utc).limit(400).all()
    return _envelope(
        {
            "timezone": "Europe/Moscow",
            "episodes": [
                {
                    "id": row.id,
                    "series_id": row.series_id,
                    "channel_id": row.channel_id,
                    "slot_utc": ensure_utc(row.slot_utc).isoformat(),
                    "status": row.status,
                    "version": row.version,
                }
                for row in rows
            ],
        }
    )


@router.post("/api/v1/calendar/propose")
def calendar_propose(user=Depends(require_roles("EDITOR", "OWNER")), db: Session = Depends(get_db)) -> dict:
    del user
    report = propose_fortnight(db, utcnow())
    return _envelope(report, "demo")


@router.patch("/api/v1/calendar/episodes/{episode_id}")
def calendar_move(
    episode_id: int,
    body: MoveBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    del user
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode missing")
    try:
        move_episode(db, episode, body.slot_utc, body.expected_version)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _envelope({"id": episode.id, "version": episode.version, "status": episode.status})


@router.get("/api/v1/programs")
def programs(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    rows = db.query(Series).order_by(Series.id).all()
    return _envelope({"programs": [{"id": row.id, "title": row.title, "min_items": row.min_items} for row in rows]})


@router.post("/api/v1/programs/{series_id}/preview")
def program_preview(series_id: str, user=Depends(require_roles("EDITOR", "OWNER")), db: Session = Depends(get_db)) -> dict:
    del user
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="series missing")
    report = propose_fortnight(db, utcnow())
    own = [item for item in report["skipped"] if item.get("series") == series_id]
    return _envelope({"series": series_id, "skipped": own, "created": report["created"], "published": 0}, "demo")


@router.get("/api/v1/insights/funnel")
def insights_funnel(channel_id: str = "", auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    return funnel(db, channel_id=channel_id)


@router.post("/api/v1/insights/measurements")
def insights_measure(
    body: MeasureBody,
    user=Depends(require_roles("EDITOR", "OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    if body.kind in {"views", "forwards"} and body.value is not None:
        raise HTTPException(status_code=422, detail="bot views are unavailable")
    row = record_manual(db, channel_id=body.channel_id, kind=body.kind, value=body.value, actor=user.username, now=utcnow())
    return _envelope({"id": row.id, "measurement_source": "manual", "value": row.value})


@router.get("/api/v1/commercial/campaigns")
def campaigns(auth=Depends(require_user), db: Session = Depends(get_db)) -> dict:
    del auth
    rows = db.query(AdCampaign).order_by(AdCampaign.id).all()
    payload = []
    for row in rows:
        actual = (
            db.query(FinanceEvent).filter_by(campaign_id=row.id, kind="actual").order_by(FinanceEvent.id.desc()).first()
        )
        payload.append(
            {
                "id": row.id,
                "advertiser": row.advertiser,
                "channel_id": row.channel_id,
                "demo": row.demo,
                "legal_status": row.legal_status,
                "actual_amount": None if actual is None else actual.amount,
            }
        )
    mode = "demo" if payload and all(item["demo"] for item in payload) else "mixed" if payload else "unavailable"
    return _envelope({"campaigns": payload}, mode)


@router.post("/api/v1/commercial/campaigns")
def create_campaign(
    body: CampaignBody,
    user=Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
) -> dict:
    if not body.demo:
        add_audit(db, actor=user.username, action="campaign", entity="ad", result="blocked")
        db.commit()
        raise HTTPException(status_code=403, detail="only demo campaigns are allowed")
    row = AdCampaign(advertiser=body.advertiser[:200], channel_id=body.channel_id, demo=True, legal_status="pending")
    db.add(row)
    db.commit()
    return _envelope({"id": row.id, "demo": True, "published": False}, "demo")


@router.post("/api/v1/system/sponsored")
def sponsored_switch(user=Depends(require_roles("OWNER")), db: Session = Depends(get_db)) -> dict:
    add_audit(db, actor=user.username, action="sponsored", entity="policy", result="blocked")
    db.commit()
    raise HTTPException(status_code=403, detail="sponsored publishing is off")
