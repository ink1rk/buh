"""Выгрузка списков. Экспорт пишется в аудит: кто, когда и сколько строк."""

from __future__ import annotations

import csv
import io

from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.context import current_context
from itms.models.audit import AuditLog
from itms.models.enums import AuditAction
from itms.services import ci_service

_COLUMNS = ("code", "name", "ci_type", "status", "criticality", "environment")


async def ci_csv(session: AsyncSession, flt: ci_service.CiFilter) -> str:
    flt.limit = min(max(flt.limit, 1), 5000)
    flt.offset = 0
    items, total = await ci_service.list_ci(session, flt)
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    for item in items:
        writer.writerow(
            [
                item.code or "",
                item.name,
                item.ci_type.value,
                item.status.value,
                item.criticality.value,
                item.environment.value,
            ]
        )
    ctx = current_context()
    session.add(
        AuditLog(
            actor_id=ctx.actor_id,
            actor_kind=ctx.actor_kind.value,
            actor_label=ctx.actor_label,
            request_id=ctx.request_id,
            entity_type="CI",
            entity_label="ci.csv",
            action=AuditAction.EXPORT,
            reason="Экспорт списка объектов",
            comment=f"строк {len(items)} из {total}",
            source="api",
            ip=ctx.ip,
        )
    )
    await session.flush()
    return buffer.getvalue()
