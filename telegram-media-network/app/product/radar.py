"""Cluster, explain, and route demo observations. No live HTTP."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import (
    ClusterMember,
    EventRelation,
    RankedCandidate,
    Source,
    SourceItem,
    SourceSnapshot,
    Story,
    StoryAlias,
    StoryCluster,
    StoryEvidence,
    TrendSample,
)
from app.core.timeutil import ensure_utc, utcnow
from app.product.intelligence import (
    MODEL,
    canonical_url,
    channel_hot_count,
    compute_trend,
    enrich_cluster,
    independent_publishers,
    items_for,
    member_count,
    publisher_of,
    record_score_revision,
    score_cluster,
    source_ids_for,
    trend_samples_for,
)

_WORD = re.compile(r"[^0-9a-zа-яё]+", re.I)


def hard_key(row: dict) -> str:
    if row.get("cve"):
        return f"cve:{row['cve']}"
    if row.get("doi"):
        return f"doi:{row['doi']}"
    if row.get("arxiv"):
        return f"arxiv:{row['arxiv']}"
    if row.get("repo") and row.get("tag"):
        return f"repo:{row['repo']}:{row['tag']}"
    url = canonical_url(row.get("url") or "")
    if url:
        return "url:" + hashlib.sha256(url.encode()).hexdigest()[:24]
    return ""


def title_key(title: str) -> str:
    norm = _WORD.sub(" ", (title or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return "title:" + norm[:180]


def import_observations(session: Session, rows: list[dict], now: datetime | None = None) -> dict:
    moment = ensure_utc(now or utcnow())
    created = 0
    duplicates = 0
    updates = 0
    skipped_future = 0
    cluster_ids: list[int] = []
    for row in rows:
        available = _coerce_available(row.get("available_at"))
        if available is not None and available > moment:
            skipped_future += 1
            continue
        _ensure_source(session, row["source_id"])
        digest = hashlib.sha256((row.get("body") or row["external_id"]).encode()).hexdigest()
        existing = (
            session.query(SourceItem)
            .filter_by(source_id=row["source_id"], external_id=row["external_id"][:300])
            .order_by(SourceItem.id)
            .first()
        )
        pub_id, pub_kind, _title = publisher_of(row["source_id"])
        if row.get("publisher_id"):
            pub_id = str(row["publisher_id"])
        origin_mode = str(row.get("origin_mode") or pub_kind or "demo")
        if existing is not None and existing.raw_hash == digest:
            duplicates += 1
            continue
        published = moment - timedelta(days=int(row.get("days_old") or 0))
        if existing is not None and existing.raw_hash != digest:
            session.add(
                SourceSnapshot(
                    source_item_id=existing.id,
                    raw_hash=existing.raw_hash,
                    body=dict(existing.raw_json or {}),
                    discovered_utc=existing.discovered_utc,
                    claimed_utc=existing.published_utc,
                    canonical_url=canonical_url(row.get("url") or ""),
                    origin_mode=existing.origin_mode,
                )
            )
            existing.raw_hash = digest
            existing.raw_json = {"demo": True, "never_publish": True, "title": row["title"], "body": row.get("body") or row["summary"]}
            existing.fetched_utc = moment
            existing.publisher_id = pub_id
            existing.origin_mode = origin_mode
            updates += 1
            item = existing
        else:
            item = SourceItem(
                source_id=row["source_id"],
                external_id=row["external_id"][:300],
                discovered_utc=moment,
                published_utc=published,
                raw_hash=digest,
                raw_json={"demo": True, "never_publish": True, "title": row["title"], "body": row.get("body") or row.get("summary")},
                fetched_utc=moment,
                publisher_id=pub_id,
                content_kind=str(row.get("content_kind") or ("cve" if row.get("cve") else "release" if row.get("tag") else "news")),
                origin_mode=origin_mode,
                lab_run_id=row.get("lab_run_id"),
                available_at=available or published,
                cassette_id=str(row.get("cassette_id") or ""),
            )
            session.add(item)
            session.flush()
            created += 1
        session.add(
            SourceSnapshot(
                source_item_id=item.id,
                raw_hash=digest,
                body=dict(item.raw_json or {}),
                discovered_utc=moment,
                claimed_utc=published,
                canonical_url=canonical_url(row.get("url") or ""),
                origin_mode=origin_mode,
            )
        )
        key = hard_key(row) or title_key(row["title"])
        cluster = session.query(StoryCluster).filter_by(cluster_key=key).one_or_none()
        story: Story | None
        relation = "update" if updates and existing is not None else "member"
        if cluster is None:
            story = _story(session, row, published, moment, key)
            cluster = StoryCluster(
                cluster_key=key,
                title=row["title"][:300],
                kind="cve" if row.get("cve") else "release" if row.get("tag") else "evergreen" if row.get("evergreen") else "event",
                status="open",
                list_name="review",
                primary_channel_id=row["channel_id"],
                first_seen=moment,
                last_seen=moment,
                updated_at=moment,
                merge_reason=f"ключ {key}",
                event_type="cve" if row.get("cve") else "release" if row.get("tag") else "preprint" if row.get("arxiv") else "evergreen" if row.get("evergreen") else "event",
                event_at=published,
                dossier_json={
                    "affected_products": row.get("product") or "",
                    "version_scope": row.get("version_scope") or "unknown",
                    "origin": "demo" if row.get("synthetic") else "fixture",
                },
                data_mode="demo",
                program_kind="evergreen" if row.get("evergreen") else "breaking",
                lab_run_id=row.get("lab_run_id"),
            )
            session.add(cluster)
            session.flush()
            session.add(
                ClusterMember(
                    cluster_id=cluster.id,
                    story_id=story.id,
                    source_item_id=item.id,
                    relation="member",
                    reason=f"новая тема по {key}",
                )
            )
        else:
            story = _primary_story(session, cluster)
            cluster.last_seen = moment
            cluster.updated_at = moment
            already = (
                session.query(ClusterMember)
                .filter_by(cluster_id=cluster.id, source_item_id=item.id, relation="member")
                .first()
            )
            if already is None:
                session.add(
                    ClusterMember(
                        cluster_id=cluster.id,
                        story_id=story.id if story else None,
                        source_item_id=item.id,
                        relation="member",
                        reason=f"{'обновление' if relation == 'update' else 'тот же ключ'} {key}",
                    )
                )
            if story is not None:
                status = _evidence_status(session, cluster, item)
                session.add(
                    StoryEvidence(
                        story_id=story.id,
                        claim_id=f"src-{item.id}",
                        source_item_id=item.id,
                        statement=row["summary"][:400],
                        evidence_excerpt=row["summary"][:160],
                        evidence_url=row["url"],
                        verified_at=None,
                        status=status,
                    )
                )
                if origin_mode == "reprint" and story.id:
                    session.add(
                        EventRelation(
                            left_cluster_id=cluster.id,
                            right_cluster_id=cluster.id,
                            relation="reprint",
                            reason="перепечатка того же издателя",
                            actor="radar",
                        )
                    )
        if row.get("stars") is not None:
            sample_at = published if row.get("star_at_published") else moment
            session.add(
                TrendSample(
                    source_item_id=item.id,
                    snapshot_utc=sample_at,
                    metric_name="github_stars",
                    value=int(row["stars"]),
                    provider=str(row.get("trend_provider") or "demo_fixture"),
                    completeness="series" if row.get("stars_series") else "single",
                )
            )
        if row.get("related_key"):
            other = session.query(StoryCluster).filter_by(cluster_key=row["related_key"]).one_or_none()
            if other is not None and other.id != cluster.id:
                session.add(
                    EventRelation(
                        left_cluster_id=cluster.id,
                        right_cluster_id=other.id,
                        relation="related",
                        reason=str(row.get("related_reason") or "связанный сюжет"),
                        actor="radar",
                    )
                )
        cluster_ids.append(cluster.id)
    _mark_similar(session)
    rank_open_clusters(session, moment)
    session.commit()
    return {
        "created": created,
        "duplicates": duplicates,
        "updates": updates,
        "observations": len(rows),
        "skipped_future": skipped_future,
        "cluster_ids": sorted(set(cluster_ids)),
    }


def _coerce_available(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def rank_open_clusters(session: Session, now: datetime) -> int:
    moment = ensure_utc(now)
    count = 0
    clusters = session.query(StoryCluster).all()
    hot_cache = {row.primary_channel_id: channel_hot_count(session, row.primary_channel_id) for row in clusters}
    for cluster in clusters:
        trend_rows = trend_samples_for(session, cluster)
        samples = len(trend_rows)
        trend = compute_trend(trend_rows)
        story = _primary_story(session, cluster)
        anchor = story.published_utc if story is not None and story.published_utc is not None else cluster.first_seen
        enrich_cluster(session, cluster, moment, anchor)
        members = member_count(session, cluster)
        source_ids = source_ids_for(session, cluster)
        source_items = items_for(session, cluster)
        publishers = independent_publishers(source_ids, source_items)
        preprint = bool(story.is_preprint) if story is not None else False
        license_state = story.license_state if story is not None else "unknown"
        hot = hot_cache.get(cluster.primary_channel_id, 0)
        cluster.trend_state = str(trend.get("state") or "unknown")
        cluster.trend_delta = trend.get("delta")
        for channel_id in _channels_for(cluster):
            dimensions, penalties, score, explanation, evidence_state, confidence = score_cluster(
                cluster,
                channel_id,
                samples=samples,
                members=members,
                source_ids=source_ids,
                now=moment,
                anchor=anchor,
                preprint=preprint,
                license_state=license_state,
                channel_hot=hot,
                trend=trend,
                publishers=publishers,
            )
            row = (
                session.query(RankedCandidate)
                .filter_by(cluster_id=cluster.id, channel_id=channel_id, model_version=MODEL)
                .one_or_none()
            )
            if row is None:
                row = RankedCandidate(cluster_id=cluster.id, channel_id=channel_id, model_version=MODEL)
                session.add(row)
            row.computed_at = moment
            row.dimensions_json = dimensions
            row.penalties_json = penalties
            row.trend_state = str(trend.get("state") or "unknown")
            row.reasons_json = list(dimensions.get("reasons") or [])
            record_score_revision(session, cluster, channel_id, dimensions=dimensions, total=score)
            row.rank_score = score
            row.confidence = confidence
            row.explanation = explanation
            row.status = evidence_state
            count += 1
        cluster.list_name = _list_name(cluster, moment, anchor)
        cluster.score_version = MODEL
    return count


def _evidence_status(session: Session, cluster: StoryCluster, item: SourceItem) -> str:
    """A URL or reprint never becomes independently_verified by itself."""
    del session
    kind = item.origin_mode or publisher_of(item.source_id)[1]
    if kind in {"reprint", "aggregator", "social_signal"}:
        return "source_supported"
    if kind in {"origin", "vendor"}:
        return "source_supported"
    return "unreviewed"


def route_cluster(session: Session, cluster: StoryCluster, channel_id: str, reason: str, actor: str) -> None:
    if not reason.strip():
        raise ValueError("reason required")
    cluster.primary_channel_id = channel_id
    cluster.manual_override = True
    cluster.merge_reason = reason.strip()[:500]
    cluster.updated_at = utcnow()
    add_audit(
        session,
        actor=actor,
        action="route",
        entity="cluster",
        entity_id=cluster.id,
        result=channel_id,
        payload={"reason": reason[:200]},
    )


def merge_into(session: Session, source_id: int, target_id: int, actor: str, reason: str) -> None:
    from app.product.intelligence import merge_clusters

    source = session.get(StoryCluster, source_id)
    target = session.get(StoryCluster, target_id)
    if source is None or target is None:
        raise ValueError("cluster missing")
    merge_clusters(session, source, target, actor, reason)


def split_member(session: Session, cluster_id: int, member_id: int, actor: str, reason: str) -> StoryCluster:
    from app.product.intelligence import split_cluster

    cluster = session.get(StoryCluster, cluster_id)
    if cluster is None:
        raise ValueError("cluster missing")
    return split_cluster(session, cluster, member_id, actor, reason)


def bulk_list(session: Session, cluster_ids: list[int], list_name: str, reason: str, actor: str) -> int:
    if list_name not in {"hot", "review", "evergreen", "backfill", "rejected", "covered"}:
        raise ValueError("unknown list")
    changed = 0
    for cluster_id in cluster_ids:
        cluster = session.get(StoryCluster, cluster_id)
        if cluster is None:
            continue
        cluster.list_name = list_name
        cluster.status = "rejected" if list_name == "rejected" else cluster.status
        cluster.manual_override = True
        cluster.merge_reason = reason[:500]
        changed += 1
    add_audit(session, actor=actor, action="bulk_list", entity="cluster", result=list_name, payload={"count": changed})
    return changed


def _list_name(cluster: StoryCluster, now: datetime, anchor: datetime) -> str:
    if cluster.manual_override and cluster.list_name in {"hot", "review", "evergreen", "backfill", "rejected", "covered"}:
        return cluster.list_name
    if cluster.program_kind == "evergreen" or cluster.kind == "evergreen":
        return "evergreen"
    age = (ensure_utc(now) - ensure_utc(anchor)).days
    if age > 30:
        return "backfill"
    if cluster.kind == "cve":
        return "review"
    return "hot"


def _channels_for(cluster: StoryCluster) -> list[str]:
    channels = [cluster.primary_channel_id or "dev"]
    extra = {
        "ai_news": "ai_tools",
        "ai_tools": "dev",
        "github": "dev",
        "cyber": "infra",
        "infra": "homelab",
        "homelab": "infra",
        "dev": "github",
        "future": "ai_news",
    }
    other = extra.get(channels[0])
    if other and other not in channels:
        channels.append(other)
    return channels


def _sample_count(session: Session, cluster: StoryCluster) -> int:
    item_ids = [
        row.source_item_id
        for row in session.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member")
        if row.source_item_id
    ]
    if not item_ids:
        return 0
    return session.query(TrendSample).filter(TrendSample.source_item_id.in_(item_ids)).count()


def _mark_similar(session: Session) -> None:
    clusters = session.query(StoryCluster).all()
    for left in clusters:
        for right in clusters:
            if right.id <= left.id or left.cluster_key == right.cluster_key:
                continue
            same_repo = left.cluster_key.startswith("repo:") and right.cluster_key.startswith("repo:")
            if same_repo:
                if left.cluster_key.rsplit(":", 1)[0] != right.cluster_key.rsplit(":", 1)[0]:
                    continue
            elif left.title != right.title:
                continue
            ratio = SequenceMatcher(None, left.title, right.title).ratio()
            if ratio < 0.86:
                continue
            exists = (
                session.query(ClusterMember)
                .filter_by(cluster_id=left.id, relation="merge_candidate", reason=f"similar:{right.id}")
                .first()
            )
            if exists:
                continue
            story = _primary_story(session, right)
            session.add(
                ClusterMember(
                    cluster_id=left.id,
                    story_id=story.id if story else None,
                    relation="merge_candidate",
                    reason=f"similar:{right.id}",
                )
            )


def _primary_story(session: Session, cluster: StoryCluster) -> Story | None:
    member = (
        session.query(ClusterMember)
        .filter_by(cluster_id=cluster.id, relation="member")
        .filter(ClusterMember.story_id.is_not(None))
        .order_by(ClusterMember.id)
        .first()
    )
    if member is None or member.story_id is None:
        return None
    return session.get(Story, member.story_id)


def _story(session: Session, row: dict, published: datetime, moment: datetime, key: str) -> Story:
    story = Story(
        canonical_url=row["url"],
        canonical_hash=hashlib.sha256(row["url"].encode()).hexdigest(),
        cluster_id=key[:300],
        repo_identity=row.get("repo") or "",
        published_utc=published,
        discovered_utc=moment,
        title=row["title"][:400],
        summary=row["summary"][:500],
        status="NEEDS_REVIEW",
        provenance_json={"demo": True, "never_publish": True, "external_id": row["external_id"]},
        primary_channel_id=row["channel_id"],
        content_kind="advisory" if row.get("cve") else "release" if row.get("tag") else "news",
        source_id=row["source_id"],
        synthetic=True,
        is_preprint=bool(row.get("arxiv")),
        license_state=str(row.get("license_state") or "unknown"),
    )
    session.add(story)
    session.flush()
    session.add(StoryAlias(alias=f"demo:{row['external_id']}"[:300], story_id=story.id))
    session.add(
        StoryEvidence(
            story_id=story.id,
            claim_id="f1",
            statement=row["summary"][:400],
            evidence_excerpt=row["summary"][:160],
            evidence_url=row["url"],
            verified_at=None,
            status="source_supported" if row.get("url") else "unreviewed",
        )
    )
    return story


def _ensure_source(session: Session, source_id: str) -> None:
    if session.get(Source, source_id) is None:
        session.add(Source(id=source_id, kind="demo", adapter="demo", enabled=False, health="offline"))
        session.flush()
