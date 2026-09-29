from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.models.cmdb import Ci, Location
from itms.models.directory import Employee
from itms.models.documents import Document
from itms.models.enums import CiStatus, Criticality, DocumentStatus, EmployeeStatus
from itms.services import audit_service


def _brief(value: Any) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    if len(text) > 64:
        return text[:61] + "…"
    return text


async def dashboard(session: AsyncSession) -> dict[str, Any]:
    """Сводка для владельца системы.

    В Phase 1 это состояние модели: объекты, размещения, документы, люди и активность.
    Задачи, инциденты, изменения и питание добавляются следующими фазами.
    """
    active_ci = select(Ci).where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None)).subquery()

    counters = {
        "ci_total": int(
            (await session.execute(select(func.count()).select_from(active_ci))).scalar_one()
        ),
        "ci_critical": int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Ci)
                    .where(
                        Ci.deleted_at.is_(None),
                        Ci.archived_at.is_(None),
                        Ci.criticality == Criticality.CRITICAL,
                    )
                )
            ).scalar_one()
        ),
        "ci_attention": int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Ci)
                    .where(
                        Ci.deleted_at.is_(None),
                        Ci.archived_at.is_(None),
                        Ci.status.in_([CiStatus.DEGRADED, CiStatus.MAINTENANCE]),
                    )
                )
            ).scalar_one()
        ),
        "locations": int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Location)
                    .where(Location.deleted_at.is_(None), Location.archived_at.is_(None))
                )
            ).scalar_one()
        ),
        "employees_active": int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Employee)
                    .where(Employee.deleted_at.is_(None), Employee.status == EmployeeStatus.ACTIVE)
                )
            ).scalar_one()
        ),
        "documents": int(
            (
                await session.execute(
                    select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
                )
            ).scalar_one()
        ),
        "documents_review_due": int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(
                        Document.deleted_at.is_(None),
                        Document.review_due_on.isnot(None),
                        Document.review_due_on <= date.today(),
                        Document.status != DocumentStatus.ARCHIVED,
                    )
                )
            ).scalar_one()
        ),
    }

    by_type = await session.execute(
        select(Ci.ci_type, func.count())
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .group_by(Ci.ci_type)
        .order_by(func.count().desc())
    )
    by_status = await session.execute(
        select(Ci.status, func.count())
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .group_by(Ci.status)
    )
    by_criticality = await session.execute(
        select(Ci.criticality, func.count())
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .group_by(Ci.criticality)
    )

    activity = await audit_service.recent_activity(session, limit=15)
    provenance = await audit_service.provenance_summary(session)

    return {
        "counters": counters,
        "ci_by_type": [{"key": str(t), "count": int(n)} for t, n in by_type],
        "ci_by_status": [{"key": str(s), "count": int(n)} for s, n in by_status],
        "ci_by_criticality": [{"key": str(c), "count": int(n)} for c, n in by_criticality],
        "data_quality": {
            "provenance": provenance,
            "ci_without_location": int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Ci)
                        .where(
                            Ci.deleted_at.is_(None),
                            Ci.archived_at.is_(None),
                            Ci.location_id.is_(None),
                        )
                    )
                ).scalar_one()
            ),
            "ci_without_owner": int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Ci)
                        .where(
                            Ci.deleted_at.is_(None),
                            Ci.archived_at.is_(None),
                            Ci.owner_employee_id.is_(None),
                        )
                    )
                ).scalar_one()
            ),
        },
        "recent_activity": [
            {
                "id": log.id,
                "occurred_at": log.occurred_at,
                "actor_label": log.actor_label,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "entity_label": log.entity_label,
                "action": log.action,
                "reason": log.reason,
                "project_id": log.project_id,
                "changes": [
                    {
                        "field": change.field,
                        "old_value": _brief(change.old_value),
                        "new_value": _brief(change.new_value),
                    }
                    for change in log.changes[:2]
                ],
            }
            for log in activity
        ],
    }
