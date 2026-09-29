"""Реестр платформы: куда смотрит маршрут и на чём он работает."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Invalid, NotFound
from itms.models.cmdb import Ci
from itms.models.network import Vlan
from itms.models.platform import AgentMcp, AgentService, K8sCluster, McpServer, ServiceRoute
from itms.models.projects import Project
from itms.models.virtualization import VirtualMachine

ENVIRONMENTS = frozenset({"PROD", "STAGE", "DEV", "OTHER"})
TRANSPORTS = frozenset({"HTTP", "SSE", "STDIO"})
AGENT_KINDS = frozenset({"OPENCODE", "OTHER"})
TARGET_KINDS = frozenset({"CLUSTER", "MCP", "AGENT", "VM", "URL"})


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _require(value: str | None, field: str) -> str:
    text = _clean(value)
    if not text:
        raise Invalid("Заполните название", field=field)
    return text


async def _project_names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(select(Project.id, Project.name).where(Project.id.in_(ids)))
    ).all()
    return {row[0]: row[1] for row in rows}


async def _names(session: AsyncSession) -> dict[str, dict[uuid.UUID, str]]:
    clusters = (await session.execute(select(K8sCluster.id, K8sCluster.name))).all()
    servers = (await session.execute(select(McpServer.id, McpServer.name))).all()
    agents = (await session.execute(select(AgentService.id, AgentService.name))).all()
    vms = (
        await session.execute(
            select(VirtualMachine.id, Ci.name).join(Ci, Ci.id == VirtualMachine.id)
        )
    ).all()
    return {
        "CLUSTER": {row[0]: row[1] for row in clusters},
        "MCP": {row[0]: row[1] for row in servers},
        "AGENT": {row[0]: row[1] for row in agents},
        "VM": {row[0]: row[1] for row in vms},
    }


async def _ensure_target(
    session: AsyncSession, kind: str, target_id: uuid.UUID | None, url: str | None
) -> None:
    if kind not in TARGET_KINDS:
        raise Invalid("Неизвестная цель маршрута", field="target_kind")
    if kind == "URL":
        if not _clean(url):
            raise Invalid("Укажите адрес назначения", field="target_url")
        return
    if target_id is None:
        raise Invalid("Выберите, куда ведёт маршрут", field="target_id")
    found = (await _names(session))[kind].get(target_id)
    if found is None:
        raise Invalid("Цель маршрута не найдена", field="target_id")


def _cluster_row(item: K8sCluster, projects: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "endpoint": item.endpoint,
        "version": item.version,
        "environment": item.environment,
        "project_id": item.project_id,
        "project_name": projects.get(item.project_id) if item.project_id else None,
        "host_id": item.host_id,
        "notes": item.notes,
    }


def _mcp_row(
    item: McpServer, projects: dict[uuid.UUID, str], clusters: dict[uuid.UUID, str]
) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "endpoint": item.endpoint,
        "transport": item.transport,
        "cluster_id": item.cluster_id,
        "cluster_name": clusters.get(item.cluster_id) if item.cluster_id else None,
        "project_id": item.project_id,
        "project_name": projects.get(item.project_id) if item.project_id else None,
        "description": item.description,
    }


async def list_clusters(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await session.execute(select(K8sCluster).order_by(K8sCluster.name))).scalars())
    projects = await _project_names(session, {row.project_id for row in rows if row.project_id})
    return [_cluster_row(row, projects) for row in rows]


async def create_cluster(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    environment = data.get("environment") or "PROD"
    if environment not in ENVIRONMENTS:
        raise Invalid("Среда кластера указана неверно", field="environment")
    item = K8sCluster(
        name=_require(data.get("name"), "name"),
        endpoint=_clean(data.get("endpoint")),
        version=_clean(data.get("version")),
        environment=environment,
        project_id=data.get("project_id"),
        host_id=data.get("host_id"),
        notes=_clean(data.get("notes")),
    )
    session.add(item)
    await session.flush()
    projects = await _project_names(session, {item.project_id} if item.project_id else set())
    return _cluster_row(item, projects)


async def delete_cluster(session: AsyncSession, cluster_id: uuid.UUID) -> None:
    item = await session.get(K8sCluster, cluster_id)
    if item is None:
        raise NotFound("Кластер не найден", entity_id=str(cluster_id))
    await session.delete(item)
    await session.flush()


async def list_mcp(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await session.execute(select(McpServer).order_by(McpServer.name))).scalars())
    projects = await _project_names(session, {row.project_id for row in rows if row.project_id})
    names = await _names(session)
    return [_mcp_row(row, projects, names["CLUSTER"]) for row in rows]


async def create_mcp(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    transport = data.get("transport") or "HTTP"
    if transport not in TRANSPORTS:
        raise Invalid("Транспорт MCP указан неверно", field="transport")
    item = McpServer(
        name=_require(data.get("name"), "name"),
        endpoint=_require(data.get("endpoint"), "endpoint"),
        transport=transport,
        cluster_id=data.get("cluster_id"),
        project_id=data.get("project_id"),
        description=_clean(data.get("description")),
    )
    session.add(item)
    await session.flush()
    projects = await _project_names(session, {item.project_id} if item.project_id else set())
    names = await _names(session)
    return _mcp_row(item, projects, names["CLUSTER"])


async def delete_mcp(session: AsyncSession, server_id: uuid.UUID) -> None:
    item = await session.get(McpServer, server_id)
    if item is None:
        raise NotFound("MCP-сервер не найден", entity_id=str(server_id))
    await session.delete(item)
    await session.flush()


async def _mcp_ids(session: AsyncSession, agent_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        await session.execute(select(AgentMcp.mcp_id).where(AgentMcp.agent_id == agent_id))
    ).all()
    return [row[0] for row in rows]


def _agent_row(
    item: AgentService,
    projects: dict[uuid.UUID, str],
    mcp_ids: list[uuid.UUID],
    mcp_names: dict[uuid.UUID, str],
) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "kind": item.kind,
        "endpoint": item.endpoint,
        "model": item.model,
        "project_id": item.project_id,
        "project_name": projects.get(item.project_id) if item.project_id else None,
        "description": item.description,
        "mcp_ids": mcp_ids,
        "mcp_names": [mcp_names[item_id] for item_id in mcp_ids if item_id in mcp_names],
    }


async def list_agents(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (await session.execute(select(AgentService).order_by(AgentService.name))).scalars()
    )
    projects = await _project_names(session, {row.project_id for row in rows if row.project_id})
    names = await _names(session)
    links = (await session.execute(select(AgentMcp))).scalars()
    by_agent: dict[uuid.UUID, list[uuid.UUID]] = {}
    for link in links:
        by_agent.setdefault(link.agent_id, []).append(link.mcp_id)
    return [
        _agent_row(row, projects, by_agent.get(row.id, []), names["MCP"]) for row in rows
    ]


async def _bind_mcp(session: AsyncSession, agent_id: uuid.UUID, mcp_ids: list[uuid.UUID]) -> None:
    known = (await _names(session))["MCP"]
    unknown = [item for item in mcp_ids if item not in known]
    if unknown:
        raise Invalid("MCP-сервер не найден", field="mcp_ids")
    existing = list(
        (await session.execute(select(AgentMcp).where(AgentMcp.agent_id == agent_id))).scalars()
    )
    for link in existing:
        await session.delete(link)
    for mcp_id in dict.fromkeys(mcp_ids):
        session.add(AgentMcp(agent_id=agent_id, mcp_id=mcp_id))
    await session.flush()


async def create_agent(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    kind = data.get("kind") or "OPENCODE"
    if kind not in AGENT_KINDS:
        raise Invalid("Тип агента указан неверно", field="kind")
    item = AgentService(
        name=_require(data.get("name"), "name"),
        kind=kind,
        endpoint=_clean(data.get("endpoint")),
        model=_clean(data.get("model")),
        project_id=data.get("project_id"),
        description=_clean(data.get("description")),
    )
    session.add(item)
    await session.flush()
    await _bind_mcp(session, item.id, list(data.get("mcp_ids") or []))
    projects = await _project_names(session, {item.project_id} if item.project_id else set())
    names = await _names(session)
    return _agent_row(item, projects, await _mcp_ids(session, item.id), names["MCP"])


async def delete_agent(session: AsyncSession, agent_id: uuid.UUID) -> None:
    item = await session.get(AgentService, agent_id)
    if item is None:
        raise NotFound("Агент не найден", entity_id=str(agent_id))
    await session.delete(item)
    await session.flush()


def _route_row(
    item: ServiceRoute,
    projects: dict[uuid.UUID, str],
    names: dict[str, dict[uuid.UUID, str]],
    vlans: dict[uuid.UUID, str],
) -> dict[str, Any]:
    target_name = item.target_url if item.target_kind == "URL" else None
    if item.target_kind != "URL" and item.target_id is not None:
        target_name = names[item.target_kind].get(item.target_id)
    return {
        "id": item.id,
        "name": item.name,
        "host": item.host,
        "path": item.path,
        "target_kind": item.target_kind,
        "target_id": item.target_id,
        "target_url": item.target_url,
        "target_name": target_name,
        "vlan_id": item.vlan_id,
        "vlan_label": vlans.get(item.vlan_id) if item.vlan_id else None,
        "project_id": item.project_id,
        "project_name": projects.get(item.project_id) if item.project_id else None,
        "notes": item.notes,
    }


async def _vlan_labels(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = (
        await session.execute(select(Vlan.id, Vlan.vid, Vlan.name).where(Vlan.id.in_(ids)))
    ).all()
    return {row[0]: f"{row[1]} {row[2]}" for row in rows}


async def list_routes(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(ServiceRoute).order_by(ServiceRoute.host, ServiceRoute.path)
    rows = list((await session.execute(stmt)).scalars())
    projects = await _project_names(session, {row.project_id for row in rows if row.project_id})
    vlans = await _vlan_labels(session, {row.vlan_id for row in rows if row.vlan_id})
    names = await _names(session)
    return [_route_row(row, projects, names, vlans) for row in rows]


async def create_route(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    kind = data.get("target_kind") or ""
    path = _clean(data.get("path")) or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    await _ensure_target(session, kind, data.get("target_id"), data.get("target_url"))
    item = ServiceRoute(
        name=_require(data.get("name"), "name"),
        host=_require(data.get("host"), "host"),
        path=path,
        target_kind=kind,
        target_id=None if kind == "URL" else data.get("target_id"),
        target_url=_clean(data.get("target_url")) if kind == "URL" else None,
        vlan_id=data.get("vlan_id"),
        project_id=data.get("project_id"),
        notes=_clean(data.get("notes")),
    )
    session.add(item)
    await session.flush()
    projects = await _project_names(session, {item.project_id} if item.project_id else set())
    vlans = await _vlan_labels(session, {item.vlan_id} if item.vlan_id else set())
    return _route_row(item, projects, await _names(session), vlans)


async def delete_route(session: AsyncSession, route_id: uuid.UUID) -> None:
    item = await session.get(ServiceRoute, route_id)
    if item is None:
        raise NotFound("Маршрут не найден", entity_id=str(route_id))
    await session.delete(item)
    await session.flush()


async def overview(session: AsyncSession) -> dict[str, Any]:
    clusters = await list_clusters(session)
    servers = await list_mcp(session)
    agents = await list_agents(session)
    routes = await list_routes(session)
    vlan_count = (await session.execute(select(func.count()).select_from(Vlan))).scalar_one()
    vm_count = (
        await session.execute(select(func.count()).select_from(VirtualMachine))
    ).scalar_one()
    return {
        "clusters": clusters,
        "mcp": servers,
        "agents": agents,
        "routes": routes,
        "counts": {
            "clusters": len(clusters),
            "mcp": len(servers),
            "agents": len(agents),
            "routes": len(routes),
            "vlans": int(vlan_count),
            "vms": int(vm_count),
        },
    }
