"""Local worker heartbeat. It is not a claim that an external site is healthy."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.models import ComponentHeartbeat
from app.core.timeutil import ensure_utc, utcnow

STALE_AFTER = timedelta(minutes=10)


def beat(session: Session, name: str, status: str, detail: str = "") -> None:
    row = session.get(ComponentHeartbeat, name)
    if row is None:
        row = ComponentHeartbeat(name=name)
        session.add(row)
    row.status = status[:40]
    row.detail = detail[:300]
    row.beat_at = utcnow()
    session.commit()


def component_view(session: Session, name: str, now=None) -> dict:
    moment = ensure_utc(now or utcnow())
    row = session.get(ComponentHeartbeat, name)
    if row is None or row.beat_at is None:
        return {"status": "missing", "detail": "no heartbeat"}
    age = moment - ensure_utc(row.beat_at)
    if age > STALE_AFTER:
        return {"status": "stale", "detail": row.detail or "heartbeat is old"}
    return {"status": row.status or "unknown", "detail": row.detail or ""}
