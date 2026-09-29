from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok
from itms.api.schemas.platform import (
    AgentRead,
    AgentWrite,
    ClusterRead,
    ClusterWrite,
    McpRead,
    McpWrite,
    PlatformOverview,
    RouteRead,
    RouteWrite,
)
from itms.domain.permissions import Permission
from itms.services import platform_service

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("", response_model=PlatformOverview, dependencies=[requires(Permission.CI_READ)])
async def platform_overview(session: SessionDep) -> PlatformOverview:
    return PlatformOverview.model_validate(await platform_service.overview(session))


@router.get(
    "/clusters", response_model=list[ClusterRead], dependencies=[requires(Permission.CI_READ)]
)
async def list_clusters(session: SessionDep) -> list[ClusterRead]:
    rows = await platform_service.list_clusters(session)
    return [ClusterRead.model_validate(row) for row in rows]


@router.post(
    "/clusters",
    response_model=ClusterRead,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_cluster(payload: ClusterWrite, session: SessionDep) -> ClusterRead:
    row = await platform_service.create_cluster(session, payload.model_dump())
    return ClusterRead.model_validate(row)


@router.delete(
    "/clusters/{cluster_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)]
)
async def delete_cluster(cluster_id: uuid.UUID, session: SessionDep) -> Ok:
    await platform_service.delete_cluster(session, cluster_id)
    return Ok()


@router.get("/mcp", response_model=list[McpRead], dependencies=[requires(Permission.CI_READ)])
async def list_mcp(session: SessionDep) -> list[McpRead]:
    return [McpRead.model_validate(row) for row in await platform_service.list_mcp(session)]


@router.post(
    "/mcp", response_model=McpRead, status_code=201, dependencies=[requires(Permission.CI_WRITE)]
)
async def create_mcp(payload: McpWrite, session: SessionDep) -> McpRead:
    return McpRead.model_validate(await platform_service.create_mcp(session, payload.model_dump()))


@router.delete("/mcp/{server_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)])
async def delete_mcp(server_id: uuid.UUID, session: SessionDep) -> Ok:
    await platform_service.delete_mcp(session, server_id)
    return Ok()


@router.get("/agents", response_model=list[AgentRead], dependencies=[requires(Permission.CI_READ)])
async def list_agents(session: SessionDep) -> list[AgentRead]:
    return [AgentRead.model_validate(row) for row in await platform_service.list_agents(session)]


@router.post(
    "/agents",
    response_model=AgentRead,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_agent(payload: AgentWrite, session: SessionDep) -> AgentRead:
    row = await platform_service.create_agent(session, payload.model_dump())
    return AgentRead.model_validate(row)


@router.delete(
    "/agents/{agent_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)]
)
async def delete_agent(agent_id: uuid.UUID, session: SessionDep) -> Ok:
    await platform_service.delete_agent(session, agent_id)
    return Ok()


@router.get("/routes", response_model=list[RouteRead], dependencies=[requires(Permission.CI_READ)])
async def list_routes(session: SessionDep) -> list[RouteRead]:
    return [RouteRead.model_validate(row) for row in await platform_service.list_routes(session)]


@router.post(
    "/routes",
    response_model=RouteRead,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_route(payload: RouteWrite, session: SessionDep) -> RouteRead:
    row = await platform_service.create_route(session, payload.model_dump())
    return RouteRead.model_validate(row)


@router.delete(
    "/routes/{route_id}", response_model=Ok, dependencies=[requires(Permission.CI_WRITE)]
)
async def delete_route(route_id: uuid.UUID, session: SessionDep) -> Ok:
    await platform_service.delete_route(session, route_id)
    return Ok()
