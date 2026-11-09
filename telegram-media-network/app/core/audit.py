from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.core.models import AuditEvent
from app.core.redact import redact_obj
from app.core.timeutil import utcnow


def add_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: object = "",
    result: str,
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor=actor[:120],
        action=action[:80],
        entity=entity[:80],
        entity_id=str(entity_id)[:80],
        result=result[:40],
        created_at=utcnow(),
        trace_id=trace_id or secrets.token_hex(8),
        payload_redacted=redact_obj(payload or {}),
    )
    session.add(event)
    return event
