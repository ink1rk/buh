from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.network import (
    CableRouteRead,
    CableRouteWrite,
    ConnectionCreate,
    ConnectionResult,
    ConnectionRow,
    ConnectionUpdate,
    FreePortsRow,
    RedundancyGroup,
    TraceResult,
)
from itms.domain.permissions import Permission
from itms.models.enums import ConnectionStatus
from itms.services import network_service

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/connections", response_model=Page[ConnectionRow],
            dependencies=[requires(Permission.CI_READ)])
async def list_connections(
    session: SessionDep,
    ci_id: uuid.UUID | None = None,
    status: Annotated[list[ConnectionStatus] | None, Query()] = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[ConnectionRow]:
    items, total = await network_service.list_connections(
        session, ci_id=ci_id, status=status, q=q, limit=limit, offset=offset
    )
    return Page[ConnectionRow](
        items=[ConnectionRow.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/connections", response_model=ConnectionResult, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_connection(payload: ConnectionCreate, session: SessionDep) -> ConnectionResult:
    result = await network_service.create_connection(session, payload.model_dump())
    return ConnectionResult(
        connection=ConnectionRow.model_validate(result["connection"]),
        warnings=result["warnings"],
    )


@router.patch("/connections/{connection_id}", response_model=ConnectionResult,
              dependencies=[requires(Permission.NETWORK_WRITE)])
async def update_connection(
    connection_id: uuid.UUID, payload: ConnectionUpdate, session: SessionDep
) -> ConnectionResult:
    result = await network_service.update_connection(
        session, connection_id, payload.model_dump(exclude_unset=True)
    )
    return ConnectionResult(
        connection=ConnectionRow.model_validate(result["connection"]),
        warnings=result["warnings"],
    )


@router.delete("/connections/{connection_id}", response_model=Ok,
               dependencies=[requires(Permission.NETWORK_WRITE)])
async def delete_connection(connection_id: uuid.UUID, session: SessionDep) -> Ok:
    await network_service.delete_connection(session, connection_id)
    return Ok()


@router.get("/interfaces/{interface_id}/trace", response_model=TraceResult,
            dependencies=[requires(Permission.CI_READ)])
async def trace_link(interface_id: uuid.UUID, session: SessionDep) -> TraceResult:
    """Сквозной путь от порта: через патч-панели до конечного устройства."""
    return TraceResult.model_validate(await network_service.trace(session, interface_id))


@router.get("/routes", response_model=list[CableRouteRead],
            dependencies=[requires(Permission.CI_READ)])
async def list_routes(session: SessionDep) -> list[CableRouteRead]:
    return [CableRouteRead.model_validate(r) for r in await network_service.list_routes(session)]


@router.post("/routes", response_model=CableRouteRead, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_route(payload: CableRouteWrite, session: SessionDep) -> CableRouteRead:
    route = await network_service.create_route(session, payload.model_dump())
    return CableRouteRead.model_validate(route)


@router.get("/reports/free-ports", response_model=list[FreePortsRow],
            dependencies=[requires(Permission.CI_READ)])
async def free_ports(session: SessionDep) -> list[FreePortsRow]:
    rows = await network_service.free_ports_report(session)
    return [FreePortsRow.model_validate(row) for row in rows]


@router.get("/reports/redundancy", response_model=list[RedundancyGroup],
            dependencies=[requires(Permission.CI_READ)])
async def redundancy(session: SessionDep) -> list[RedundancyGroup]:
    rows = await network_service.redundancy_report(session)
    return [RedundancyGroup.model_validate(row) for row in rows]
