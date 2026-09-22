from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Page
from itms.api.schemas.ops import (
    AuditLogRead,
    DashboardRead,
    ImportJobRead,
    ImportMappingUpdate,
    MetaResponse,
    SearchHitRead,
    SearchResponse,
)
from itms.core.config import settings
from itms.domain.permissions import Permission
from itms.models.enums import (
    CI_STATUS_TRANSITIONS,
    LOCATION_PARENTS,
    AuditAction,
    CiStatus,
    CiType,
    Criticality,
    DocumentKind,
    DocumentStatus,
    EmployeeStatus,
    Environment,
    ImportTarget,
    LocationType,
    RelationType,
    SupportLine,
    UserRole,
)
from itms.services import audit_service, dashboard_service, import_service, search_service

search_router = APIRouter(prefix="/search", tags=["search"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])
import_router = APIRouter(prefix="/imports", tags=["imports"])
dashboard_router = APIRouter(tags=["dashboard"])


@search_router.get("", response_model=SearchResponse,
                   dependencies=[requires(Permission.CI_READ)])
async def global_search(
    session: SessionDep,
    q: str = Query(min_length=1, max_length=200),
    entity_type: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    hits = await search_service.search(
        session, q, entity_types=entity_type, limit=limit, offset=offset
    )
    counts = await search_service.count_by_type(session, q)
    return SearchResponse(
        query=q,
        hits=[SearchHitRead(**asdict(hit)) for hit in hits],
        counts=counts,
    )


@audit_router.get("", response_model=Page[AuditLogRead],
                  dependencies=[requires(Permission.AUDIT_READ)])
async def list_audit(
    session: SessionDep,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: Annotated[list[AuditAction] | None, Query()] = None,
    change_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    field: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AuditLogRead]:
    items, total = await audit_service.list_audit(
        session,
        audit_service.AuditFilter(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=action,
            change_id=change_id,
            project_id=project_id,
            task_id=task_id,
            field=field,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        ),
    )
    return Page[AuditLogRead](
        items=[AuditLogRead.model_validate(log) for log in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@import_router.post("", response_model=ImportJobRead, status_code=201,
                    dependencies=[requires(Permission.IMPORT_RUN)])
async def create_import(
    session: SessionDep,
    target: ImportTarget,
    file: UploadFile = File(...),
) -> ImportJobRead:
    content = await file.read()
    job = await import_service.create_job(
        session, target=target, filename=file.filename or "import.csv", content=content
    )
    return ImportJobRead.model_validate(job)


@import_router.get("/{job_id}", response_model=ImportJobRead,
                   dependencies=[requires(Permission.IMPORT_RUN)])
async def get_import(job_id: uuid.UUID, session: SessionDep) -> ImportJobRead:
    return ImportJobRead.model_validate(await import_service.get_job(session, job_id))


@import_router.patch("/{job_id}/mapping", response_model=ImportJobRead,
                     dependencies=[requires(Permission.IMPORT_RUN)])
async def update_mapping(
    job_id: uuid.UUID, payload: ImportMappingUpdate, session: SessionDep
) -> ImportJobRead:
    job = await import_service.get_job(session, job_id)
    job.mapping = payload.mapping
    return ImportJobRead.model_validate(job)


@import_router.post("/{job_id}/validate", response_model=ImportJobRead,
                    dependencies=[requires(Permission.IMPORT_RUN)])
async def validate_import(job_id: uuid.UUID, session: SessionDep) -> ImportJobRead:
    job = await import_service.get_job(session, job_id)
    return ImportJobRead.model_validate(await import_service.validate_job(session, job))


@import_router.post("/{job_id}/apply", response_model=ImportJobRead,
                    dependencies=[requires(Permission.IMPORT_RUN)])
async def apply_import(job_id: uuid.UUID, session: SessionDep) -> ImportJobRead:
    job = await import_service.get_job(session, job_id)
    return ImportJobRead.model_validate(await import_service.apply_job(session, job))


@dashboard_router.get("/dashboard", response_model=DashboardRead,
                      dependencies=[requires(Permission.CI_READ)])
async def dashboard(session: SessionDep) -> DashboardRead:
    return DashboardRead.model_validate(await dashboard_service.dashboard(session))


@dashboard_router.get("/meta", response_model=MetaResponse,
                      dependencies=[requires(Permission.CI_READ)])
async def meta() -> MetaResponse:
    return MetaResponse(
        ci_types=[e.value for e in CiType],
        ci_statuses=[e.value for e in CiStatus],
        ci_status_transitions={
            source.value: sorted(t.value for t in targets)
            for source, targets in CI_STATUS_TRANSITIONS.items()
        },
        criticalities=[e.value for e in Criticality],
        environments=[e.value for e in Environment],
        location_types=[e.value for e in LocationType],
        location_parents={
            child.value: sorted(p.value for p in parents)
            for child, parents in LOCATION_PARENTS.items()
        },
        relation_types=[e.value for e in RelationType],
        document_kinds=[e.value for e in DocumentKind],
        document_statuses=[e.value for e in DocumentStatus],
        employee_statuses=[e.value for e in EmployeeStatus],
        support_lines=[e.value for e in SupportLine],
        user_roles=[e.value for e in UserRole],
        audit_actions=[e.value for e in AuditAction],
        import_targets=[e.value for e in ImportTarget],
        import_fields={
            target.value: list(fields) for target, fields in import_service.FIELD_ALIASES.items()
        },
        import_required_fields={
            target.value: list(fields)
            for target, fields in import_service.REQUIRED_FIELDS.items()
        },
        power_defaults={
            "voltage_single_v": settings.power_voltage_single_v,
            "voltage_three_v": settings.power_voltage_three_v,
            "power_factor": settings.power_factor_default,
            "derating": settings.power_derating_default,
            "reserve_target_pct": settings.power_reserve_target_pct,
            "measurement_ttl_days": settings.power_measurement_ttl_days,
            "phase_disbalance_limit_pct": settings.power_phase_disbalance_limit_pct,
        },
    )
