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
    RankedCandidate,
    Source,
    SourceItem,
    Story,
    StoryAlias,
    StoryCluster,
    StoryEvidence,
    TrendSample,
)
from app.core.timeutil import ensure_utc, utcnow

MODEL = "radar-v2"
_WORD = re.compile(r"[^0-9a-zа-яё]+", re.I)


def hard_key(row: dict) -> str:
    if row.get("cve"):
        return f"cve:{row['cve']}"
    if row.get("arxiv"):
        return f"arxiv:{row['arxiv']}"
    if row.get("repo") and row.get("tag"):
        return f"repo:{row['repo']}:{row['tag']}"
    url = (row.get("url") or "").strip()
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
    for row in rows:
        _ensure_source(session, row["source_id"])
        existing = (
            session.query(SourceItem)
            .filter_by(source_id=row["source_id"], external_id=row["external_id"][:300])
            .one_or_none()
        )
        if existing is not None:
            duplicates += 1
            continue
        published = moment - timedelta(days=int(row.get("days_old") or 0))
        item = SourceItem(
            source_id=row["source_id"],
            external_id=row["external_id"][:300],
            discovered_utc=moment,
            published_utc=published,
            raw_hash=hashlib.sha256(row["external_id"].encode()).hexdigest(),
            raw_json={"demo": True, "never_publish": True, "title": row["title"]},
            fetched_utc=moment,
        )
        session.add(item)
        session.flush()
        created += 1
        key = hard_key(row) or title_key(row["title"])
        cluster = session.query(StoryCluster).filter_by(cluster_key=key).one_or_none()
        story: Story | None
        if cluster is None:
            story = _story(session, row, published, moment, key)
            cluster = StoryCluster(
                cluster_key=key,
                title=row["title"][:300],
                kind="cve" if row.get("cve") else "release" if row.get("tag") else "event",
                status="open",
                list_name="review",
                primary_channel_id=row["channel_id"],
                first_seen=moment,
                last_seen=moment,
                updated_at=moment,
                merge_reason=f"ключ {key}",
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
            session.add(
                ClusterMember(
                    cluster_id=cluster.id,
                    story_id=story.id if story else None,
                    source_item_id=item.id,
                    relation="member",
                    reason=f"тот же ключ {key}",
                )
            )
            if story is not None:
                session.add(
                    StoryEvidence(
                        story_id=story.id,
                        claim_id=f"src-{item.id}",
                        source_item_id=item.id,
                        statement=row["summary"][:400],
                        evidence_excerpt=row["summary"][:160],
                        evidence_url=row["url"],
                        verified_at=None,
                        status="extracted",
                    )
                )
        if row.get("stars") is not None:
            session.add(
                TrendSample(
                    source_item_id=item.id,
                    snapshot_utc=moment,
                    metric_name="github_stars",
                    value=int(row["stars"]),
                    provider="demo_fixture",
                    completeness="single",
                )
            )
    _mark_similar(session)
    rank_open_clusters(session, moment)
    session.commit()
    return {"created": created, "duplicates": duplicates, "observations": len(rows)}


def rank_open_clusters(session: Session, now: datetime) -> int:
    moment = ensure_utc(now)
    count = 0
    clusters = session.query(StoryCluster).all()
    for cluster in clusters:
        samples = _sample_count(session, cluster)
        story = _primary_story(session, cluster)
        anchor = story.published_utc if story is not None and story.published_utc is not None else cluster.first_seen
        for channel_id in _channels_for(cluster):
            dimensions, penalties, score, explanation = _score(cluster, channel_id, samples, moment, anchor)
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
            row.rank_score = score
            row.confidence = 70 if channel_id == cluster.primary_channel_id else 40
            row.explanation = explanation
            row.status = "ranked"
            count += 1
        cluster.list_name = _list_name(cluster, moment, anchor)
    return count


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


def _score(cluster: StoryCluster, channel_id: str, samples: int, now: datetime, anchor: datetime) -> tuple[dict, dict, int, str]:
    age_days = max(0, (ensure_utc(now) - ensure_utc(anchor)).days)
    primary = channel_id == cluster.primary_channel_id
    dimensions = {
        "relevance": 20 if primary else 8,
        "freshness": 18 if age_days <= 3 else 6,
        "novelty": 14 if cluster.kind != "event" or primary else 8,
        "practicality": 12,
        "evidence_quality": 15 if cluster.merge_reason.startswith("ключ") or "тот же" in cluster.merge_reason else 10,
        "trend_signal": None if samples < 2 else 4,
        "risk": 4 if cluster.kind == "cve" else 0,
    }
    penalties = {}
    if samples < 2:
        penalties["insufficient_history"] = 0
    if age_days > 30:
        penalties["backfill"] = 8
    total = sum(value for value in dimensions.values() if isinstance(value, int))
    total -= sum(penalties.values())
    total = max(0, min(100, total))
    trend = "неизвестен: меньше двух сопоставимых снимков" if samples < 2 else "посчитан по двум и более снимкам"
    explanation = (
        f"Канал {'основной' if primary else 'запасной'}: relevance {dimensions['relevance']}, "
        f"freshness {dimensions['freshness']}, novelty {dimensions['novelty']}, "
        f"practicality {dimensions['practicality']}, evidence {dimensions['evidence_quality']}. "
        f"trend_signal {trend}. Риск {dimensions['risk']}."
    )
    return dimensions, penalties, total, explanation


def _list_name(cluster: StoryCluster, now: datetime, anchor: datetime) -> str:
    if cluster.manual_override and cluster.list_name in {"hot", "review", "evergreen", "backfill", "rejected", "covered"}:
        return cluster.list_name
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
            status="extracted",
        )
    )
    return story


def _ensure_source(session: Session, source_id: str) -> None:
    if session.get(Source, source_id) is None:
        session.add(Source(id=source_id, kind="demo", adapter="demo", enabled=False, health="offline"))
        session.flush()
