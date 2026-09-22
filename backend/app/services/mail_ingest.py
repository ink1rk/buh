"""Письмо про деньги → событие финансового календаря.

Чек и счёт не заводят диалог у ассистента: отвечать там некому. Но дату
и сумму из них нельзя терять — иначе платёж всплывает сюрпризом. Повтор того же письма не создаёт второе событие: сначала по Message-ID,
если его нет — по отправителю, теме, дате и сумме.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import CalendarEvent

TYPE_HINTS = (
    ("подписк", "subscription"),
    ("subscription", "subscription"),
    ("налог", "tax"),
    ("штраф", "fine"),
    ("жкх", "utilities"),
    ("квитанц", "utilities"),
    ("зарплат", "salary"),
    ("ипотек", "credit"),
    ("кредит", "credit"),
)


def _event_type(subject: str) -> str:
    text = (subject or "").lower()
    for needle, kind in TYPE_HINTS:
        if needle in text:
            return kind
    return "payment"


def _fingerprint(payload: dict, day: date, amount: float) -> str:
    message_id = (payload.get("message_id") or "").strip()
    if message_id:
        return message_id
    sender = (payload.get("sender") or "").strip().lower()
    subject = (payload.get("subject") or "").strip().lower()
    return f"{sender}|{subject}|{day.isoformat()}|{amount:.2f}"


async def ingest_mail(db: AsyncSession, payload: dict) -> dict:
    subject = (payload.get("subject") or "").strip() or "Письмо про оплату"
    sender = (payload.get("sender") or "").strip()
    raw_date = payload.get("event_date")
    if raw_date:
        day = date.fromisoformat(str(raw_date)[:10])
    else:
        day = date.today()
    amount = float(payload.get("amount") or 0)
    external_id = _fingerprint(payload, day, amount)
    if external_id:
        existing = (
            await db.execute(
                select(CalendarEvent).where(CalendarEvent.external_id == external_id)
            )
        ).scalar_one_or_none()
        if existing:
            return {"duplicate": True, "id": existing.id}

    notes = (payload.get("text") or "").strip()[:500]
    if sender:
        notes = f"{sender}\n{notes}".strip()

    row = CalendarEvent(
        title=subject[:200],
        event_type=_event_type(subject),
        amount=amount,
        event_date=day,
        notes=notes,
        source="mail",
        external_id=external_id,
        color="#fbbf24",
    )
    db.add(row)
    await db.flush()
    return {"duplicate": False, "id": row.id, "title": row.title,
            "amount": row.amount, "event_date": row.event_date.isoformat()}
