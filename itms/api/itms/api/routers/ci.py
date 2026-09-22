from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.cmdb import (
    CiCreate,
    CiRead,
    CiUpdate,
    ProvenanceEntry,
    RelatedItem,
    RelationCreate,
)
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.documents import DocumentRead
from itms.api.schemas.ops import AuditLogRead
from itms.domain.permissions import Permission
from itms.models.cmdb import Ci
from itms.models.enums import CiStatus, CiType
from itms.services import ci_service, document_service

router = APIRouter(prefix="/ci", tags=["ci"])


def _to_read(ci: Ci, tags: list[str]) -> CiRead:
    payload = CiRead.model_validate(ci)
    payload.tags = tags
    return payload


@router.get("", response_model=Page[CiRead], dependencies=[requires(Permission.CI_READ)])
async def list_ci(
    session: SessionDep,
    q: str | None = None,
    ci_type: Annotated[list[CiType] | None, Query()] = None,
    status: Annotated[list[CiStatus] | None, Query()] = None,
    location_id: uuid.UUID | None = None,
    include_sublocations: bool = True,
    owner_employee_id: uuid.UUID | None = None,
    tag: Annotated[list[str] | None, Query()] = None,
    archived: bool = False,
    sort: str = "name",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[CiRead]:
    items, total = await ci_service.list_ci(
        session,
        ci_service.CiFilter(
            q=q,
            ci_type=ci_type,
            status=status,
            location_id=location_id,
            include_sublocations=include_sublocations,
            owner_employee_id=owner_employee_id,
            tag=tag,
            archived=archived,
            sort=sort,
            limit=limit,
            offset=offset,
        ),
    )
    tags = await ci_service.tags_for_many(session, [ci.id for ci in items])
    return Page[CiRead](
        items=[_to_read(ci, tags.get(ci.id, [])) for ci in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CiRead, status_code=201,
             dependencies=[requires(Permission.CI_WRITE)])
async def create_ci(payload: CiCreate, session: SessionDep) -> CiRead:
    ci = await ci_service.create_ci(session, payload.model_dump(exclude_unset=True))
    return _to_read(ci, await ci_service.get_tags(session, ci.id))


@router.get("/stats", response_model=dict, dependencies=[requires(Permission.CI_READ)])
async def ci_stats(session: SessionDep) -> dict[str, Any]:
    return await ci_service.stats(session)


@router.get("/{ci_id}", response_model=CiRead, dependencies=[requires(Permission.CI_READ)])
async def get_ci(ci_id: uuid.UUID, session: SessionDep) -> CiRead:
    ci = await ci_service.get_ci(session, ci_id)
    return _to_read(ci, await ci_service.get_tags(session, ci.id))


@router.patch("/{ci_id}", response_model=CiRead, dependencies=[requires(Permission.CI_WRITE)])
async def update_ci(ci_id: uuid.UUID, payload: CiUpdate, session: SessionDep) -> CiRead:
    ci = await ci_service.update_ci(session, ci_id, payload.model_dump(exclude_unset=True))
    return _to_read(ci, await ci_service.get_tags(session, ci.id))


@router.post("/{ci_id}/archive", response_model=CiRead,
             dependencies=[requires(Permission.CI_WRITE)])
async def archive_ci(ci_id: uuid.UUID, session: SessionDep) -> CiRead:
    ci = await ci_service.archive_ci(session, ci_id)
    return _to_read(ci, await ci_service.get_tags(session, ci.id))


@router.post("/{ci_id}/restore", response_model=CiRead,
             dependencies=[requires(Permission.CI_WRITE)])
async def restore_ci(ci_id: uuid.UUID, session: SessionDep) -> CiRead:
    ci = await ci_service.restore_ci(session, ci_id)
    return _to_read(ci, await ci_service.get_tags(session, ci.id))


@router.delete("/{ci_id}", response_model=Ok, dependencies=[requires(Permission.CI_DELETE)])
async def delete_ci(ci_id: uuid.UUID, session: SessionDep) -> Ok:
    """Мягкое удаление. Для критических объектов запрещено — только архив или RETIRED."""
    await ci_service.delete_ci(session, ci_id)
    return Ok()


@router.get("/{ci_id}/related", response_model=dict[str, list],
            dependencies=[requires(Permission.CI_READ)])
async def related(ci_id: uuid.UUID, session: SessionDep) -> dict[str, list[Any]]:
    return await ci_service.related(session, ci_id)


@router.get("/{ci_id}/history", response_model=list[AuditLogRead],
            dependencies=[requires(Permission.CI_READ)])
async def history(
    ci_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogRead]:
    logs = await ci_service.history(session, ci_id, limit=limit, offset=offset)
    return [AuditLogRead.model_validate(log) for log in logs]


@router.get("/{ci_id}/provenance", response_model=list[ProvenanceEntry],
            dependencies=[requires(Permission.CI_READ)])
async def provenance(
    ci_id: uuid.UUID, field: str, session: SessionDep
) -> list[ProvenanceEntry]:
    """Кто, когда, почему и в рамках чего изменил конкретный параметр объекта."""
    entries = await ci_service.field_provenance(session, ci_id, field)
    return [ProvenanceEntry.model_validate(entry) for entry in entries]


@router.get("/{ci_id}/documents", response_model=list[DocumentRead],
            dependencies=[requires(Permission.CI_READ)])
async def ci_documents(ci_id: uuid.UUID, session: SessionDep) -> list[DocumentRead]:
    docs = await document_service.documents_for_entity(session, "CI", ci_id)
    return [DocumentRead.model_validate(doc) for doc in docs]


relations_router = APIRouter(prefix="/relations", tags=["ci"])


@relations_router.post("", response_model=RelatedItem, status_code=201,
                       dependencies=[requires(Permission.CI_WRITE)])
async def create_relation(payload: RelationCreate, session: SessionDep) -> RelatedItem:
    relation = await ci_service.create_relation(session, payload.model_dump(exclude_unset=True))
    target = relation.target
    return RelatedItem(
        relation_id=relation.id,
        rel_type=relation.rel_type,
        direction="outgoing",
        criticality=relation.criticality,
        description=relation.description,
        ci={
            "id": target.id,
            "name": target.name,
            "code": target.code,
            "ci_type": target.ci_type,
            "status": target.status,
        },
    )


@relations_router.delete("/{relation_id}", response_model=Ok,
                         dependencies=[requires(Permission.CI_WRITE)])
async def delete_relation(relation_id: uuid.UUID, session: SessionDep) -> Ok:
    await ci_service.delete_relation(session, relation_id)
    return Ok()
