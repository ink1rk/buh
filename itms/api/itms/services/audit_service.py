from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.models.audit import AuditChange, AuditLog
from itms.models.enums import AuditAction


@dataclass(slots=True)
class AuditFilter:
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    action: list[AuditAction] | None = None
    change_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    field: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 50
    offset: int = 0


async def list_audit(session: AsyncSession, flt: AuditFilter) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    if flt.entity_type:
        stmt = stmt.where(AuditLog.entity_type == flt.entity_type)
    if flt.entity_id:
        stmt = stmt.where(AuditLog.entity_id == flt.entity_id)
    if flt.actor_id:
        stmt = stmt.where(AuditLog.actor_id == flt.actor_id)
    if flt.action:
        stmt = stmt.where(AuditLog.action.in_(flt.action))
    if flt.change_id:
        stmt = stmt.where(AuditLog.change_id == flt.change_id)
    if flt.project_id:
        stmt = stmt.where(AuditLog.project_id == flt.project_id)
    if flt.task_id:
        stmt = stmt.where(AuditLog.task_id == flt.task_id)
    if flt.date_from:
        stmt = stmt.where(AuditLog.occurred_at >= flt.date_from)
    if flt.date_to:
        stmt = stmt.where(AuditLog.occurred_at <= flt.date_to)
    if flt.field:
        stmt = stmt.where(
            AuditLog.id.in_(select(AuditChange.audit_log_id).where(AuditChange.field == flt.field))
        )

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = await session.execute(
        stmt.order_by(AuditLog.occurred_at.desc()).limit(flt.limit).offset(flt.offset)
    )
    return list(rows.scalars().unique()), int(total)


async def provenance_summary(session: AsyncSession) -> dict[str, Any]:
    """Насколько полно заполнено происхождение изменений.

    Показатель эксплуатационного качества данных: изменения без причины и без ссылки
    на проект, изменение или задачу через год объяснить будет нечем.
    """
    total = (
        await session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(
                [AuditAction.UPDATE, AuditAction.STATUS, AuditAction.ARCHIVE]
            ))
        )
    ).scalar_one()
    with_provenance = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action.in_([AuditAction.UPDATE, AuditAction.STATUS, AuditAction.ARCHIVE]),
                func.coalesce(
                    AuditLog.change_id,
                    AuditLog.project_id,
                    AuditLog.task_id,
                    AuditLog.document_id,
                ).isnot(None)
                | AuditLog.reason.isnot(None),
            )
        )
    ).scalar_one()
    return {
        "changes_total": int(total),
        "changes_with_provenance": int(with_provenance),
        "coverage_pct": round(100 * with_provenance / total, 1) if total else 100.0,
    }


async def recent_activity(session: AsyncSession, limit: int = 15) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)
    )
    return list(rows.scalars().unique())
