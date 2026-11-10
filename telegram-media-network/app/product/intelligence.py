"""Radar 4.0: publishers, real trends, and versioned rank-v4. No live HTTP."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import (
    ClusterMember,
    ScoreRevision,
    SourceItem,
    Story,
    StoryCluster,
    StoryRelation,
    TrendSample,
)
from app.core.timeutil import ensure_utc

MODEL = "rank-v4"
WEIGHTS = {
    "relevance": 20,
    "freshness": 18,
    "evidence": 16,
    "novelty": 12,
    "practicality": 12,
    "urgency": 8,
    "density": 8,
    "scarcity": 6,
}

SOURCE_ROLES = {
    "cisa_kev": ("vulnerability_catalog", 18, "каталог уязвимостей"),
    "github_releases": ("vendor_release", 16, "релиз репозитория"),
    "github_search": ("repository", 12, "карточка репозитория"),
    "huggingface": ("model_card", 14, "карточка модели"),
    "arxiv_ai": ("preprint", 10, "препринт"),
    "arxiv_science": ("preprint", 10, "препринт"),
    "hackernews": ("social_signal", 6, "социальный пересказ"),
    "kubernetes": ("vendor_docs", 16, "документация вендора"),
    "pypi_updates": ("package_index", 12, "индекс пакетов"),
    "cloudflare_changelog": ("vendor_docs", 16, "журнал вендора"),
    "rss_mirror": ("reprint", 4, "перепечатка"),
}

PUBLISHERS = {
    "cisa_kev": ("cisa", "origin", "CISA"),
    "github_releases": ("github", "vendor", "GitHub"),
    "github_search": ("github", "origin", "GitHub"),
    "huggingface": ("huggingface", "origin", "Hugging Face"),
    "arxiv_ai": ("arxiv", "origin", "arXiv"),
    "arxiv_science": ("arxiv", "origin", "arXiv"),
    "hackernews": ("hackernews", "aggregator", "Hacker News"),
    "kubernetes": ("kubernetes", "vendor", "Kubernetes"),
    "pypi_updates": ("pypi", "origin", "PyPI"),
    "cloudflare_changelog": ("cloudflare", "vendor", "Cloudflare"),
    "rss_mirror": ("mirror", "reprint", "RSS-перепечатка"),
}

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "yclid"}
ORIGIN_KINDS = {"origin", "vendor"}


def canonical_url(url: str) -> str:
    """Strip tracking params and fragments. Identity query keys stay."""
    parts = urlsplit((url or "").strip())
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in TRACKING]
    host = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    scheme = (parts.scheme or "https").lower()
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def source_role(source_id: str) -> tuple[str, int, str]:
    return SOURCE_ROLES.get(source_id, ("unknown", 8, "роль не задана"))


def publisher_of(source_id: str) -> tuple[str, str, str]:
    return PUBLISHERS.get(source_id, (source_id or "unknown", "unknown", "неизвестный издатель"))


def independent_publishers(source_ids: list[str], items: list[SourceItem] | None = None) -> set[str]:
    """Aggregators and reprints of the same issuer do not add a second confirmation."""
    found: set[str] = set()
    if items:
        for item in items:
            kind = item.origin_mode or publisher_of(item.source_id)[1]
            pub = item.publisher_id or publisher_of(item.source_id)[0]
            if kind in ORIGIN_KINDS and pub:
                found.add(pub)
        return found
    for source_id in source_ids:
        pub, kind, _title = publisher_of(source_id)
        if kind in ORIGIN_KINDS:
            found.add(pub)
    return found


def compute_trend(samples: list[TrendSample]) -> dict:
    """Trend exists only for two or more comparable points of the same metric and provider."""
    grouped: dict[tuple[str, str], list[TrendSample]] = {}
    for row in samples:
        if row.value is None:
            continue
        grouped.setdefault((row.metric_name, row.provider or ""), []).append(row)
    comparable: list[TrendSample] = []
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda item: ensure_utc(item.snapshot_utc))
        if len(ordered) >= 2:
            comparable = ordered
            break
    if len(comparable) < 2:
        return {
            "state": "unknown",
            "delta": None,
            "signal": None,
            "reason": "неизвестен: меньше двух сопоставимых снимков",
            "values": [{"at": ensure_utc(row.snapshot_utc).isoformat(), "value": row.value, "metric": row.metric_name} for row in samples],
        }
    first, last = comparable[0], comparable[-1]
    if first.value is None or last.value is None:
        return {
            "state": "unknown",
            "delta": None,
            "signal": None,
            "reason": "неизвестен: меньше двух сопоставимых снимков",
            "values": [{"at": ensure_utc(row.snapshot_utc).isoformat(), "value": row.value, "metric": row.metric_name} for row in samples],
        }
    delta = int(last.value) - int(first.value)
    state = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return {
        "state": state,
        "delta": delta,
        "signal": delta,
        "from": first.value,
        "to": last.value,
        "metric": first.metric_name,
        "provider": first.provider,
        "at_from": ensure_utc(first.snapshot_utc).isoformat(),
        "at_to": ensure_utc(last.snapshot_utc).isoformat(),
        "reason": f"{first.metric_name}: {first.value} → {last.value} (Δ {delta}, {first.provider or 'fixture'})",
        "values": [{"at": ensure_utc(row.snapshot_utc).isoformat(), "value": row.value} for row in comparable],
    }


def score_cluster(
    cluster: StoryCluster,
    channel_id: str,
    *,
    samples: int,
    members: int,
    source_ids: list[str],
    now: datetime,
    anchor: datetime,
    preprint: bool,
    license_state: str,
    channel_hot: int,
    trend: dict | None = None,
    publishers: set[str] | None = None,
    weights: dict[str, int] | None = None,
    formula_version: str = MODEL,
) -> tuple[dict, dict, int, str, str, int]:
    scale = weights or WEIGHTS
    age_days = max(0, (ensure_utc(now) - ensure_utc(anchor)).days)
    primary = channel_id == cluster.primary_channel_id
    roles = [source_role(source_id) for source_id in source_ids] or [source_role("")]
    best_trust = max(role[1] for role in roles)
    social_only = bool(source_ids) and all(source_role(source_id)[0] in {"social_signal", "reprint"} for source_id in source_ids)
    independent = len(publishers if publishers is not None else independent_publishers(source_ids))
    relevance = scale["relevance"] if primary else 8
    if cluster.kind == "cve" and channel_id != "cyber":
        relevance = 4
    if cluster.kind == "release" and channel_id in {"github", "dev", "ai_tools"}:
        relevance = min(scale["relevance"], relevance + 2)
    freshness = 18 if age_days <= 1 else 12 if age_days <= 7 else 6 if age_days <= 21 else 2 if age_days <= 30 else 0
    evidence = min(16, best_trust - 2 + min(4, independent))
    if preprint:
        evidence = min(evidence, 10)
    novelty = 12 if members <= 1 else 10 if members == 2 else 8
    if cluster.kind == "release":
        novelty = 12
    practicality = 12 if cluster.kind in {"release"} or channel_id in {"ai_tools", "dev", "homelab"} else 8
    if preprint:
        practicality = 6
    if social_only:
        practicality = 4
    urgency = 8 if cluster.kind == "cve" and age_days <= 7 and channel_id == "cyber" else 4 if cluster.kind == "cve" else 0
    density = min(8, members * 2 + (2 if cluster.merge_reason else 0))
    scarcity = 6 if channel_hot < 4 else 3 if channel_hot < 10 else 1
    trend_info = trend or {"state": "unknown", "signal": None, "reason": "неизвестен: меньше двух сопоставимых снимков"}
    if trend is None and samples < 2:
        trend_info = {"state": "unknown", "signal": None, "reason": "неизвестен: меньше двух сопоставимых снимков"}
    dimensions = {
        "relevance": relevance,
        "freshness": freshness,
        "evidence": evidence,
        "novelty": novelty,
        "practicality": practicality,
        "urgency": urgency,
        "density": density,
        "scarcity": scarcity,
        "trend_signal": trend_info.get("signal"),
        "formula_version": formula_version,
    }
    penalties: dict[str, int] = {}
    if samples < 2 or trend_info.get("state") == "unknown":
        penalties["insufficient_history"] = 0
    if age_days > 30:
        penalties["backfill"] = 10
    if not primary:
        penalties["duplicate_across_network"] = 12
    if social_only:
        penalties["social_only"] = 6
    if cluster.kind == "cve" and not (cluster.dossier_json or {}).get("affected_products"):
        penalties["unclear_scope"] = 8
    if license_state in {"unknown", ""} and cluster.kind == "release":
        penalties["unverified_license"] = 4
    total = sum(int(value) for key, value in dimensions.items() if isinstance(value, int) and key != "trend_signal")
    total -= sum(penalties.values())
    total = max(0, min(100, total))
    evidence_state = "partial" if independent >= 1 else "insufficient"
    if independent >= 2:
        evidence_state = "extracted"
    if preprint:
        evidence_state = "partial"
    confidence = min(90, 30 + independent * 20 + (0 if trend_info.get("state") == "unknown" else 10))
    if social_only:
        confidence = min(confidence, 35)
    roles_text = ", ".join(sorted({role[2] for role in roles}))
    trend_text = str(trend_info.get("reason") or "неизвестен: меньше двух сопоставимых снимков")
    ranked = sorted(
        ((key, int(value)) for key, value in dimensions.items() if isinstance(value, int) and key != "trend_signal"),
        key=lambda item: item[1],
        reverse=True,
    )
    reasons = [f"{name} {score}" for name, score in ranked[:3]]
    dimensions["reasons"] = reasons
    explanation = (
        f"Канал {'основной' if primary else 'запасной'}: relevance {relevance}, freshness {freshness}, "
        f"evidence {evidence} ({roles_text}, независимых издателей {independent}), novelty {novelty}, "
        f"practicality {practicality}, urgency {urgency}, density {density}, scarcity {scarcity}. "
        f"trend_signal {trend_text}. "
        f"evidence_state {evidence_state}, confidence {confidence} — не выводятся из итогового счёта. "
        f"формула {formula_version}. причины: {', '.join(reasons)}."
        + ("" if primary else " Второй канал без самостоятельного ракурса: duplicate_across_network.")
    )
    return dimensions, penalties, total, explanation, evidence_state, confidence


def enrich_cluster(session: Session, cluster: StoryCluster, now: datetime, anchor: datetime) -> None:
    members = session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").all()
    items: list[SourceItem] = []
    source_ids: list[str] = []
    for member in members:
        if member.source_item_id:
            item = session.get(SourceItem, member.source_item_id)
            if item is not None:
                source_ids.append(item.source_id)
                items.append(item)
    story = None
    for member in members:
        if member.story_id:
            story = session.get(Story, member.story_id)
            if story is not None:
                break
    age_days = max(0, (ensure_utc(now) - ensure_utc(anchor)).days)
    independent = independent_publishers(source_ids, items)
    dossier = dict(cluster.dossier_json or {})
    dossier.update(
        {
            "source_roles": [source_role(source_id)[0] for source_id in source_ids],
            "publishers": sorted(independent),
            "claim_count": 1 if story is not None else 0,
            "independent_primary_sources": len(independent),
            "evidence_completeness": "partial" if independent else "insufficient",
            "affected_products": dossier.get("affected_products") or ("Demo Catalog App" if cluster.kind == "cve" else ""),
            "version_scope": dossier.get("version_scope") or "unknown",
            "license_status": story.license_state if story is not None else "unknown",
            "preprint_status": "preprint" if story is not None and story.is_preprint else "not_preprint",
            "freshness_class": "backfill" if age_days > 30 else "fresh" if age_days <= 3 else "aging",
            "evergreen_potential": cluster.program_kind == "evergreen" or (cluster.kind in {"release"} and age_days > 7),
            "repost_risk": "duplicate_across_network" if not cluster.primary_channel_id else "low",
            "editorial_risks": ["synthetic_demo"],
            "candidate_channels": [cluster.primary_channel_id],
        }
    )
    cluster.dossier_json = dossier
    cluster.event_type = (
        "cve"
        if cluster.kind == "cve"
        else "release"
        if cluster.kind == "release"
        else "preprint"
        if story and story.is_preprint
        else cluster.event_type or "event"
    )
    cluster.event_at = anchor
    cluster.last_change_at = now
    cluster.score_version = MODEL


def merge_clusters(session: Session, source: StoryCluster, target: StoryCluster, actor: str, reason: str) -> None:
    if source.id == target.id:
        raise ValueError("same cluster")
    if not reason.strip():
        raise ValueError("reason required")
    if source.cluster_key.startswith("cve:") and target.cluster_key.startswith("cve:") and source.cluster_key != target.cluster_key:
        raise ValueError("different CVE")
    if source.cluster_key.startswith("repo:") and target.cluster_key.startswith("repo:") and source.cluster_key != target.cluster_key:
        raise ValueError("different release")
    for member in session.query(ClusterMember).filter_by(cluster_id=source.id).all():
        member.cluster_id = target.id
        member.reason = f"merge:{reason[:120]}"
    source.status = "merged"
    source.list_name = "covered"
    source.manual_override = True
    session.add(
        StoryRelation(
            left_cluster_id=target.id,
            right_cluster_id=source.id,
            relation="merged",
            reason=reason[:500],
            actor=actor,
        )
    )
    add_audit(session, actor=actor, action="merge", entity="cluster", entity_id=target.id, result="merged")


def split_cluster(session: Session, cluster: StoryCluster, member_id: int, actor: str, reason: str) -> StoryCluster:
    member = session.get(ClusterMember, member_id)
    if member is None or member.cluster_id != cluster.id:
        raise ValueError("member missing")
    if not reason.strip():
        raise ValueError("reason required")
    created = StoryCluster(
        cluster_key=f"split:{cluster.id}:{member.id}",
        title=cluster.title,
        kind=cluster.kind,
        status="open",
        list_name="review",
        primary_channel_id=cluster.primary_channel_id,
        first_seen=cluster.first_seen,
        last_seen=cluster.last_seen,
        merge_reason=reason[:500],
        manual_override=True,
        event_type=cluster.event_type,
        dossier_json={"split_from": cluster.id},
        data_mode=cluster.data_mode,
        program_kind=cluster.program_kind,
    )
    session.add(created)
    session.flush()
    member.cluster_id = created.id
    member.reason = f"split:{reason[:120]}"
    session.add(
        StoryRelation(
            left_cluster_id=cluster.id,
            right_cluster_id=created.id,
            relation="split",
            reason=reason[:500],
            actor=actor,
        )
    )
    add_audit(session, actor=actor, action="split", entity="cluster", entity_id=created.id, result="split")
    return created


def samples_for(session: Session, cluster: StoryCluster) -> int:
    item_ids = [
        row.source_item_id
        for row in session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member")
        if row.source_item_id
    ]
    if not item_ids:
        return 0
    return session.query(TrendSample).filter(TrendSample.source_item_id.in_(item_ids)).count()


def trend_samples_for(session: Session, cluster: StoryCluster) -> list[TrendSample]:
    item_ids = [
        row.source_item_id
        for row in session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member")
        if row.source_item_id
    ]
    if not item_ids:
        return []
    return session.query(TrendSample).filter(TrendSample.source_item_id.in_(item_ids)).all()


def source_ids_for(session: Session, cluster: StoryCluster) -> list[str]:
    ids: list[str] = []
    for member in session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member"):
        if member.source_item_id:
            item = session.get(SourceItem, member.source_item_id)
            if item is not None:
                ids.append(item.source_id)
    return ids


def items_for(session: Session, cluster: StoryCluster) -> list[SourceItem]:
    found: list[SourceItem] = []
    for member in session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member"):
        if member.source_item_id:
            item = session.get(SourceItem, member.source_item_id)
            if item is not None:
                found.append(item)
    return found


def member_count(session: Session, cluster: StoryCluster) -> int:
    return session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").count()


def channel_hot_count(session: Session, channel_id: str) -> int:
    return (
        session.query(StoryCluster)
        .filter(StoryCluster.primary_channel_id == channel_id, StoryCluster.list_name != "rejected", StoryCluster.status != "merged")
        .count()
    )


def record_score_revision(
    session: Session,
    cluster: StoryCluster,
    channel_id: str,
    *,
    dimensions: dict,
    total: int,
    weights: dict | None = None,
) -> None:
    session.add(
        ScoreRevision(
            cluster_id=cluster.id,
            channel_id=channel_id,
            formula_version=str(dimensions.get("formula_version") or MODEL),
            weights_json=dict(weights or WEIGHTS),
            dimensions_json=dimensions,
            total=total,
        )
    )
