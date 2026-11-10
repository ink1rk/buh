"""Counts that come from this database. Missing audience numbers stay unknown."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.models import (
    AdCampaign,
    AudienceMetric,
    Booking,
    ClusterMember,
    Creative,
    FinanceEvent,
    MediaAsset,
    Placement,
    Post,
    PublishingOutbox,
    SourceItem,
    Story,
    StoryCluster,
)
from app.core.timeutil import ensure_utc, utcnow


def funnel(session: Session, *, channel_id: str = "", now: datetime | None = None) -> dict:
    moment = ensure_utc(now or utcnow())
    stories = session.query(Story)
    posts = session.query(Post)
    if channel_id:
        stories = stories.filter(Story.primary_channel_id == channel_id)
        posts = posts.filter(Post.channel_id == channel_id)
    ingested = _ingested_for_channel(session, channel_id)
    unique = stories.count()
    shortlisted = stories.filter(Story.score_total >= 60).count()
    drafted = posts.filter(Post.review_status != "REJECTED").count()
    reviewed = posts.filter(Post.review_status != "NEEDS_REVIEW").count()
    approved = posts.filter(Post.review_status.in_(("APPROVED", "SCHEDULED", "SENDING", "PUBLISHED"))).count()
    scheduled = session.query(PublishingOutbox).filter(PublishingOutbox.state.in_(("scheduled", "sending")))
    if channel_id:
        scheduled = scheduled.filter(PublishingOutbox.channel_id == channel_id)
    published = posts.filter(Post.review_status == "PUBLISHED").count()
    extra_members = (
        session.query(ClusterMember)
        .join(StoryCluster, StoryCluster.id == ClusterMember.cluster_id)
        .filter(ClusterMember.relation == "member")
    )
    if channel_id:
        extra_members = extra_members.filter(StoryCluster.primary_channel_id == channel_id)
    member_rows = extra_members.count()
    duplicates = max(0, member_rows - unique)
    return {
        "data_mode": "measured",
        "as_of": moment.isoformat(),
        "channel_id": channel_id,
        "formula": (
            "ingested = source_items linked to clusters assigned to the channel "
            "(or all source_items if channel is empty); unique = stories on that channel; "
            "duplicates = extra cluster members beyond unique stories"
        ),
        "stages": {
            "ingested": ingested,
            "unique": unique,
            "shortlisted": shortlisted,
            "drafted": drafted,
            "reviewed": reviewed,
            "approved": approved,
            "scheduled": scheduled.count(),
            "published": published,
        },
        "duplicates": duplicates,
        "card_failures": session.query(MediaAsset).filter_by(status="stale").count(),
        "views": "н/д",
        "members": "н/д",
        "views_source": "unknown",
        "members_source": "unknown",
    }


def _ingested_for_channel(session: Session, channel_id: str) -> int:
    query = session.query(SourceItem.id).join(ClusterMember, ClusterMember.source_item_id == SourceItem.id).join(
        StoryCluster, StoryCluster.id == ClusterMember.cluster_id
    )
    if channel_id:
        query = query.filter(StoryCluster.primary_channel_id == channel_id)
    return query.distinct().count()


def record_manual(session: Session, *, channel_id: str, kind: str, value: int | None, actor: str, now: datetime) -> AudienceMetric:
    row = AudienceMetric(
        channel_id=channel_id,
        period_at=ensure_utc(now),
        kind=kind,
        value=value,
        measurement_source="manual",
        verified_by=actor,
        created_at=ensure_utc(now),
    )
    session.add(row)
    session.commit()
    return row


def seed_demo_campaigns(session: Session, now: datetime) -> int:
    if session.query(AdCampaign).filter_by(demo=True).count() >= 2:
        return 0
    moment = ensure_utc(now)
    made = 0
    for name, channel_id in (("DEMO Учебный рекламодатель А", "ai_news"), ("DEMO Учебный рекламодатель Б", "dev")):
        campaign = AdCampaign(
            advertiser=name,
            channel_id=channel_id,
            price="",
            currency="RUB",
            period="не согласован",
            marked=False,
            legal_status="pending",
            demo=True,
            created_at=moment,
        )
        session.add(campaign)
        session.flush()
        booking = Booking(
            campaign_id=campaign.id,
            channel_id=channel_id,
            slot_utc=moment + timedelta(days=3),
            status="planned",
            demo=True,
        )
        session.add(booking)
        session.flush()
        creative = Creative(
            campaign_id=campaign.id,
            body="DEMO. Рекламный текст не подготовлен и не отправляется.",
            disclosure_status="pending",
            demo=True,
        )
        session.add(creative)
        session.flush()
        session.add(Placement(booking_id=booking.id, creative_id=creative.id, status="planned", demo=True))
        session.add(
            FinanceEvent(
                campaign_id=campaign.id,
                kind="planned",
                amount=None,
                note="Сумма не согласована",
                demo=True,
            )
        )
        session.add(
            FinanceEvent(
                campaign_id=campaign.id,
                kind="actual",
                amount=None,
                note="Факта оплаты нет",
                demo=True,
            )
        )
        made += 1
    session.commit()
    return made
