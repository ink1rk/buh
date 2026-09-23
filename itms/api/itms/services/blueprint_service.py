"""Установка шаблонов платформ в граф. Повтор не создаёт вторую копию кода."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict
from itms.domain.platform_blueprints import LINKS, NODES
from itms.models.cmdb import Ci
from itms.models.enums import CiStatus, Criticality, Environment
from itms.services import ci_service


async def install_blueprints(session: AsyncSession) -> dict[str, int]:
    created = 0
    skipped = 0
    ids: dict[str, Any] = {}
    for node in NODES:
        existing = (
            await session.execute(select(Ci).where(Ci.code == node.code).limit(1))
        ).scalar_one_or_none()
        if existing is None:
            existing = await ci_service.create_ci(
                session,
                {
                    "ci_type": node.ci_type,
                    "name": node.name,
                    "code": node.code,
                    "status": CiStatus.PLANNED,
                    "criticality": Criticality.LOW,
                    "environment": Environment.TEST,
                    "description": node.description,
                    "attributes": dict(node.attributes),
                },
            )
            created += 1
        else:
            skipped += 1
        ids[node.code] = existing.id

    links_created = 0
    links_skipped = 0
    for link in LINKS:
        try:
            await ci_service.create_relation(
                session,
                {
                    "source_ci_id": ids[link.source],
                    "target_ci_id": ids[link.target],
                    "rel_type": link.rel_type,
                },
            )
            links_created += 1
        except Conflict:
            links_skipped += 1
    return {
        "nodes_created": created,
        "nodes_skipped": skipped,
        "links_created": links_created,
        "links_skipped": links_skipped,
    }
