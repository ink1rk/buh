"""Counts that come from this database. Missing audience numbers stay unknown."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.models import (
    AdCampaign,
    AudienceMetric,
    Booking,
    Creative,
    FinanceEvent,
    MediaAsset,
    Placement,
    Post,
    PublishingOutbox,
    SourceItem,
    Story,
)
from app.core.timeutil import ensure_utc, utcnow


def funnel(session: Session, *, channel_id: str = "", now: datetime | None = None) -> dict:
    moment = ensure_utc(now or utcnow())
    stories = session.query(Story)
    posts = session.query(Post)
    items = session.query(SourceItem)
    if channel_id:
        stories = stories.filter(Story.primary_channel_id == channel_id)
        posts = posts.filter(Post.channel_id == channel_id)
        items = items.filter(SourceItem.source_id != "")
    drafted = posts.filter(Post.review_status != "REJECTED")
    approved = posts.filter(Post.review_status.in_(("APPROVED", "SCHEDULED", "SENDING", "PUBLISHED")))
    scheduled = session.query(PublishingOutbox).filter(PublishingOutbox.state.in_(("scheduled", "sending")))
    published = posts.filter(Post.review_status == "PUBLISHED")
    if channel_id:
        scheduled = scheduled.filter(PublishingOutbox.channel_id == channel_id)
    unique = stories.count()
    ingested = items.count()
    return {
        "data_mode": "measured",
        "as_of": moment.isoformat(),
        "channel_id": channel_id,
        "formula": "counts of source_items, stories, posts and outbox rows in this database",
        "stages": {
            "ingested": ingested,
            "unique": unique,
            "shortlisted": session.query(Story).filter(Story.score_total >= 60).count() if not channel_id else stories.filter(Story.score_total >= 60).count(),
            "drafted": drafted.count(),
            "reviewed": posts.filter(Post.review_status != "NEEDS_REVIEW").count(),
            "approved": approved.count(),
            "scheduled": scheduled.count(),
            "published": published.count(),
        },
        "duplicates": max(0, ingested - unique) if not channel_id else None,
        "card_failures": session.query(MediaAsset).filter_by(status="stale").count(),
        "views": "н/д",
        "members": "н/д",
    }


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
