"""Offline commercial OS. No send, no invented revenue."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import AdCampaign, Channel, ExpenseRecord, FinanceEvent, RateCard, SalesLead
from app.core.timeutil import ensure_utc

SEGMENTS = (
    ("AI-продукты", "ai_news"),
    ("B2B ИБ", "cyber"),
    ("Хостинг и инфраструктура", "infra"),
    ("DevTools", "dev"),
    ("Self-hosted и железо", "homelab"),
    ("SaaS", "ai_tools"),
    ("Open-source экосистема", "github"),
    ("Наука и R&D", "future"),
)

PACKAGES = (
    ("single", "Одиночное размещение"),
    ("series", "Серия"),
    ("special", "Спецпроект"),
    ("network", "Несколько каналов"),
)


def seed_commercial(session: Session, now: datetime) -> dict:
    moment = ensure_utc(now)
    leads = 0
    if session.query(SalesLead).count() == 0:
        for index, (segment, channel_id) in enumerate(SEGMENTS):
            session.add(
                SalesLead(
                    advertiser=f"DEMO сегмент {segment}",
                    segment=segment,
                    stage=("lead", "contact", "discussion", "offer")[index % 4],
                    channel_id=channel_id,
                    notes="Учебный лид. Спроса и договора нет.",
                    demo=True,
                    created_at=moment,
                )
            )
            leads += 1
    cards = 0
    if session.query(RateCard).count() == 0:
        for package, title in PACKAGES:
            session.add(RateCard(title=title, package=package, price=None, status="draft", demo=True))
            cards += 1
    expenses = 0
    if session.query(ExpenseRecord).count() == 0:
        for kind, note in (("infra", "хостинг, план"), ("editorial", "редактура, план"), ("design", "макеты, план")):
            session.add(ExpenseRecord(kind=kind, amount=None, note=note, demo=True, period_at=moment))
            expenses += 1
    session.commit()
    return {"leads": leads, "rate_cards": cards, "expenses": expenses}


def media_kit(session: Session) -> dict:
    channels = []
    for channel in session.query(Channel).order_by(Channel.id):
        channels.append(
            {
                "id": channel.id,
                "title": channel.title,
                "category": channel.category,
                "audience": "пока не измерены",
                "reach": "пока не измерены",
                "formats": ["карточка 1280×720", "подпись Telegram"],
            }
        )
    actuals = session.query(FinanceEvent).filter_by(kind="actual", demo=False).all()
    measured = [row.amount for row in actuals if row.amount is not None]
    return {
        "data_mode": "demo",
        "audience": "н/д",
        "reach": "н/д",
        "rules": "Реклама не публикуется без legal approval и SPONSORED_ENABLED.",
        "channels": channels,
        "packages": [{"package": row.package, "title": row.title, "price": row.price} for row in session.query(RateCard)],
        "actual_revenue": None if not measured else sum(measured),
        "actual_revenue_label": "н/д" if not measured else str(sum(measured)),
    }


def forecast(session: Session) -> dict:
    planned = session.query(FinanceEvent).filter_by(kind="planned").all()
    actual = session.query(FinanceEvent).filter_by(kind="actual").all()
    demo_campaigns = session.query(AdCampaign).filter_by(demo=True).count()
    live_campaigns = session.query(AdCampaign).filter_by(demo=False).count()
    actual_amounts = [row.amount for row in actual if row.amount is not None and not row.demo]
    return {
        "data_mode": "mixed" if demo_campaigns and live_campaigns else "demo" if demo_campaigns else "measured",
        "label": "оценка/план",
        "planned_amount": None,
        "actual_amount": None if not actual_amounts else sum(actual_amounts),
        "actual_label": "н/д",
        "demo_campaigns": demo_campaigns,
        "live_campaigns": live_campaigns,
        "margin": "неполная: нет подтверждённых затрат и выручки",
        "planned_notes": [row.note for row in planned],
    }
