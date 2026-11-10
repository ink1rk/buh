"""Offline commercial OS. No send, no invented revenue."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import (
    AdCampaign,
    Channel,
    CommercialLineItem,
    CommercialOffer,
    ExpenseRecord,
    FinanceEvent,
    RateCard,
    SalesLead,
)
from app.core.timeutil import ensure_utc, utcnow

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
    actual_amount = None if not actual_amounts else sum(actual_amounts)
    planned_amounts = [row.amount for row in planned if row.amount is not None and not row.demo]
    planned_amount = None if not planned_amounts else sum(planned_amounts)
    return {
        "data_mode": "mixed" if demo_campaigns and live_campaigns else "demo" if demo_campaigns else "measured",
        "label": "оценка/план",
        "currency": "RUB",
        "period": "текущая база, не календарный месяц рынка",
        "planned_amount": planned_amount,
        "actual_amount": actual_amount,
        "actual_label": "н/д" if actual_amount is None else str(actual_amount),
        "planned_label": "н/д" if planned_amount is None else str(planned_amount),
        "demo_campaigns": demo_campaigns,
        "live_campaigns": live_campaigns,
        "margin": "неполная: нет подтверждённых затрат и выручки",
        "planned_notes": [row.note for row in planned],
        "source": "finance_events.kind=actual AND demo=false AND amount IS NOT NULL",
    }


def create_offer(session: Session, lead: SalesLead, *, title: str, package: str, channel_id: str, actor: str) -> CommercialOffer:
    offer = CommercialOffer(
        lead_id=lead.id,
        title=title[:200],
        status="draft",
        price=None,
        price_kind="proposal",
        notes="Цена — предложение, не рыночная стоимость. Аудитория не измерена.",
        demo=True,
        history_json=[{"at": utcnow().isoformat(), "actor": actor, "event": "created"}],
    )
    session.add(offer)
    session.flush()
    session.add(
        CommercialLineItem(
            offer_id=offer.id,
            package=package,
            channel_id=channel_id or lead.channel_id,
            materials_count=1,
            price=None,
            status="proposed",
        )
    )
    session.flush()
    history = list(lead.history_json or [])
    history.append({"at": utcnow().isoformat(), "actor": actor, "event": "offer", "offer_id": offer.id})
    lead.history_json = history
    lead.stage = "offer"
    lead.offer_version = (lead.offer_version or 1) + 1
    return offer


def reserve_offer(session: Session, offer: CommercialOffer, slot_utc, actor: str) -> CommercialOffer:
    item = session.query(CommercialLineItem).filter_by(offer_id=offer.id).order_by(CommercialLineItem.id).first()
    if item is None:
        raise ValueError("no line")
    item.slot_utc = slot_utc
    item.status = "reserved"
    offer.status = "reserved"
    history = list(offer.history_json or [])
    history.append({"at": utcnow().isoformat(), "actor": actor, "event": "reserved"})
    offer.history_json = history
    return offer


def cancel_offer(session: Session, offer: CommercialOffer, actor: str) -> CommercialOffer:
    offer.status = "cancelled"
    for item in session.query(CommercialLineItem).filter_by(offer_id=offer.id):
        item.status = "cancelled"
    history = list(offer.history_json or [])
    history.append({"at": utcnow().isoformat(), "actor": actor, "event": "cancelled"})
    offer.history_json = history
    return offer


def finance_csv(session: Session) -> str:
    lines = ["kind,campaign_id,amount,currency,demo,note"]
    for row in session.query(FinanceEvent).order_by(FinanceEvent.id):
        amount = "" if row.amount is None else str(row.amount)
        lines.append(f"{row.kind},{row.campaign_id},{amount},{row.currency},{row.demo},{row.note.replace(',', ' ')}")
    return "\n".join(lines) + "\n"
