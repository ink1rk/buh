"""Research desk: one dossier per cluster, claims with evidence, no invented facts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import (
    ClaimEvidence,
    ClusterMember,
    EditorialClaim,
    EntityMention,
    EventRelation,
    Post,
    SourceItem,
    Story,
    StoryCluster,
    StoryDossier,
    StoryEvidence,
)
from app.core.timeutil import ensure_utc, utcnow
from app.product.intelligence import independent_publishers, items_for, publisher_of, source_ids_for

CLAIM_STATUSES = (
    "unreviewed",
    "source_supported",
    "independently_verified",
    "conflicted",
    "unsupported",
    "expired",
)


def build_dossier(session: Session, cluster: StoryCluster, now: datetime | None = None) -> StoryDossier:
    moment = ensure_utc(now or utcnow())
    row = session.query(StoryDossier).filter_by(cluster_id=cluster.id).one_or_none()
    if row is None:
        row = StoryDossier(cluster_id=cluster.id, data_mode=cluster.data_mode or "demo")
        session.add(row)
    story = None
    members = session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").order_by(ClusterMember.id).all()
    timeline = []
    for member in members:
        item = session.get(SourceItem, member.source_item_id) if member.source_item_id else None
        if member.story_id and story is None:
            story = session.get(Story, member.story_id)
        timeline.append(
            {
                "source_item_id": member.source_item_id,
                "relation": member.relation,
                "reason": member.reason,
                "at": item.published_utc.isoformat() if item and item.published_utc else None,
                "publisher": item.publisher_id if item else "",
                "origin_mode": item.origin_mode if item else "",
            }
        )
    dossier = dict(cluster.dossier_json or {})
    unknowns = []
    if cluster.kind == "cve":
        if not dossier.get("affected_products"):
            unknowns.append("затронутые продукты не названы источником")
        if not dossier.get("version_scope") or dossier.get("version_scope") == "unknown":
            unknowns.append("версии не подтверждены")
        unknowns.append("эксплуатация в дикой природе: не подтверждено")
        unknowns.append("CVSS: нет в источнике" if "cvss" not in (story.summary.lower() if story else "") else "CVSS только если есть в источнике")
    if cluster.kind == "release" or (story and story.content_kind == "release"):
        unknowns.append("лицензия не подтверждена" if not story or story.license_state in {"", "unknown"} else "")
    if story and story.is_preprint:
        unknowns.append("это препринт, не рецензированная работа")
        unknowns.append("размер исследования источником не задан")
    unknowns = [item for item in unknowns if item]
    relations = session.query(EventRelation).filter(
        (EventRelation.left_cluster_id == cluster.id) | (EventRelation.right_cluster_id == cluster.id)
    ).all()
    contradictions = [rel.reason for rel in relations if rel.relation in {"conflicted", "contradicted"}]
    why = {
        cluster.primary_channel_id: _why_for(cluster.primary_channel_id, cluster, story),
    }
    row.summary = (story.summary if story else cluster.title)[:500]
    row.timeline_json = timeline
    row.entities_json = _entities(cluster, story, dossier)
    row.contradictions_json = contradictions
    row.unknowns_json = unknowns
    row.why_json = why
    row.valid_until = cluster.event_at
    row.license_note = story.license_state if story else "unknown"
    row.data_mode = cluster.data_mode or "demo"
    row.updated_at = moment
    session.query(EntityMention).filter_by(cluster_id=cluster.id).delete()
    for entity in row.entities_json:
        session.add(
            EntityMention(
                cluster_id=cluster.id,
                kind=entity.get("kind") or "product",
                name=entity.get("name") or "",
                version=entity.get("version") or "",
                note=entity.get("note") or "",
            )
        )
    session.flush()
    return row


def dossier_payload(session: Session, cluster: StoryCluster) -> dict:
    row = session.query(StoryDossier).filter_by(cluster_id=cluster.id).one_or_none() or build_dossier(session, cluster)
    items = items_for(session, cluster)
    pubs = independent_publishers(source_ids_for(session, cluster), items)
    evidence = []
    story_ids = [member.story_id for member in session.query(ClusterMember).filter_by(cluster_id=cluster.id) if member.story_id]
    if story_ids:
        evidence = session.query(StoryEvidence).filter(StoryEvidence.story_id.in_(story_ids)).all()
    return {
        "id": row.id,
        "cluster_id": cluster.id,
        "title": cluster.title,
        "kind": cluster.kind,
        "channel_id": cluster.primary_channel_id,
        "summary": row.summary,
        "timeline": row.timeline_json,
        "entities": row.entities_json,
        "contradictions": row.contradictions_json,
        "unknowns": row.unknowns_json,
        "why": row.why_json,
        "license_note": row.license_note,
        "data_mode": row.data_mode,
        "independent_publishers": sorted(pubs),
        "trend_state": cluster.trend_state,
        "trend_delta": cluster.trend_delta,
        "evidence": [
            {
                "claim_id": item.claim_id,
                "text": item.statement,
                "url": item.evidence_url,
                "status": item.status,
                "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            }
            for item in evidence
        ],
        "synthetic": True,
        "never_publish": True,
    }


def verify_claim(
    session: Session,
    claim: EditorialClaim,
    *,
    actor: str,
    method: str,
    second_publisher: str,
    now: datetime | None = None,
) -> EditorialClaim:
    moment = ensure_utc(now or utcnow())
    if method != "independent_check" or not second_publisher.strip():
        raise ValueError("independent verification requires a second publisher and method")
    publishers = {second_publisher.strip()}
    if claim.evidence_url:
        # URL of the original source is not a second issuer.
        publishers.add("original")
    if len({item for item in publishers if item != "original"}) < 1 or second_publisher.strip() in {"", "url"}:
        raise ValueError("url is not independent verification")
    origin = ""
    post = session.get(Post, claim.post_id)
    if post is not None:
        story = session.get(Story, post.story_id)
        if story is not None:
            origin = publisher_of(story.source_id)[0]
    if second_publisher.strip() == origin:
        raise ValueError("same publisher is not independent")
    claim.status = "independently_verified"
    claim.method = method
    claim.actor = actor
    claim.checked_at = moment
    session.add(
        ClaimEvidence(
            claim_row_id=claim.id,
            url=claim.evidence_url,
            excerpt=claim.excerpt or claim.text[:240],
            publisher_id=second_publisher.strip(),
            snapshot_utc=moment,
            method=method,
            actor=actor,
        )
    )
    add_audit(session, actor=actor, action="verify_claim", entity="claim", entity_id=claim.id, result="independently_verified")
    return claim


def retract_verification(session: Session, claim: EditorialClaim, actor: str) -> EditorialClaim:
    claim.status = "source_supported" if claim.evidence_url else "unreviewed"
    claim.actor = actor
    claim.method = "retracted"
    add_audit(session, actor=actor, action="retract_claim", entity="claim", entity_id=claim.id, result=claim.status)
    return claim


def invalidate_on_edit(session: Session, post: Post) -> None:
    rows = session.query(EditorialClaim).filter_by(post_id=post.id, draft_version=post.draft_version).all()
    for claim in rows:
        if claim.status == "independently_verified":
            claim.status = "unreviewed"
            claim.invalidated_at = utcnow()
            claim.method = "stale_after_edit"


def _why_for(channel_id: str, cluster: StoryCluster, story: Story | None) -> str:
    table = {
        "ai_news": "что произошло и что источник реально утверждает",
        "ai_tools": "практический сценарий и ограничения по первоисточнику",
        "github": "репозиторий, тег и то, что сказано о лицензии",
        "cyber": "риск, затронутые версии и что не подтверждено",
        "infra": "эксплуатационные последствия",
        "homelab": "применимость дома и требования источника",
        "dev": "что меняется для разработчика",
        "future": "метод исследования и статус препринта",
    }
    extra = story.summary[:180] if story else cluster.title
    return f"{table.get(channel_id, 'редакционный интерес')}: {extra}"


def _entities(cluster: StoryCluster, story: Story | None, dossier: dict) -> list[dict]:
    rows = []
    product = dossier.get("affected_products") or ""
    if product:
        rows.append({"kind": "product", "name": product, "version": dossier.get("version_scope") or "", "note": ""})
    if story and story.repo_identity:
        rows.append({"kind": "repo", "name": story.repo_identity, "version": "", "note": story.license_state})
    if cluster.kind == "cve":
        rows.append({"kind": "cve", "name": cluster.cluster_key.replace("cve:", ""), "version": "", "note": "учебная запись"})
    return rows
