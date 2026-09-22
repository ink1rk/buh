"""Схемы: раскладка отдельно, свойства объектов и кабелей — из модели."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from itms.core.errors import Conflict, NotFound
from itms.domain.diagram import layered_layout
from itms.models.cmdb import Ci, CiRelation, Location
from itms.models.diagram import Diagram, DiagramEdge, DiagramNode
from itms.models.enums import ConnectionStatus, DiagramNodeKind, DiagramType
from itms.models.network import Connection, Device, Interface

ACTIVE_CABLE = (
    ConnectionStatus.ACTIVE,
    ConnectionStatus.RESERVED,
    ConnectionStatus.PLANNED,
    ConnectionStatus.FAULTY,
)


async def list_diagrams(session: AsyncSession) -> list[Diagram]:
    rows = await session.execute(select(Diagram).order_by(Diagram.name))
    return list(rows.scalars())


async def get_diagram(session: AsyncSession, diagram_id: uuid.UUID) -> Diagram:
    diagram = await session.get(Diagram, diagram_id)
    if diagram is None:
        raise NotFound("Схема не найдена", entity_id=str(diagram_id))
    return diagram


async def _nodes(session: AsyncSession, diagram_id: uuid.UUID) -> list[DiagramNode]:
    rows = await session.execute(
        select(DiagramNode)
        .where(DiagramNode.diagram_id == diagram_id)
        .order_by(DiagramNode.y, DiagramNode.x)
    )
    return list(rows.scalars())


async def _location_ids(session: AsyncSession, location_id: uuid.UUID) -> list[uuid.UUID]:
    root = await session.get(Location, location_id)
    if root is None:
        raise NotFound("Размещение не найдено", entity_id=str(location_id))
    rows = await session.execute(
        select(Location.id).where(
            or_(Location.id == root.id, Location.path.like(f"{root.path} / %"))
        )
    )
    return list(rows.scalars())


async def create_diagram(session: AsyncSession, data: dict[str, Any]) -> Diagram:
    diagram = Diagram(
        name=data["name"].strip(),
        diagram_type=DiagramType(data.get("diagram_type", DiagramType.NETWORK)),
        location_id=data.get("location_id"),
        description=data.get("description"),
        scope={"location_id": str(data["location_id"])} if data.get("location_id") else {},
    )
    session.add(diagram)
    await session.flush()
    if data.get("autofill") and diagram.location_id:
        await autofill(session, diagram)
    return diagram


async def update_diagram(
    session: AsyncSession, diagram_id: uuid.UUID, data: dict[str, Any]
) -> Diagram:
    diagram = await get_diagram(session, diagram_id)
    if data.get("name"):
        diagram.name = data["name"].strip()
    if "description" in data:
        diagram.description = data["description"]
    await session.flush()
    return diagram


async def delete_diagram(session: AsyncSession, diagram_id: uuid.UUID) -> None:
    diagram = await get_diagram(session, diagram_id)
    await session.delete(diagram)
    await session.flush()


async def autofill(session: AsyncSession, diagram: Diagram) -> Diagram:
    """Кладёт на схему объекты выбранного размещения и связи между ними."""
    if diagram.location_id is None:
        raise Conflict("Для автонаполнения укажите размещение", code_hint="scope_required")
    location_ids = await _location_ids(session, diagram.location_id)
    stmt = select(Ci).where(
        Ci.location_id.in_(location_ids),
        Ci.deleted_at.is_(None),
        Ci.archived_at.is_(None),
    )
    if diagram.diagram_type == DiagramType.NETWORK:
        stmt = stmt.where(Ci.ci_type == "DEVICE")
    cis = list((await session.execute(stmt.order_by(Ci.name))).scalars())
    present = {node.ci_id for node in await _nodes(session, diagram.id)}
    for ci in cis:
        if ci.id in present:
            continue
        session.add(
            DiagramNode(
                diagram_id=diagram.id,
                ci_id=ci.id,
                node_kind=DiagramNodeKind.CI,
                x=0,
                y=0,
                label=ci.name,
            )
        )
    await session.flush()
    await autolayout(session, diagram)
    await sync_edges(session, diagram)
    return diagram


async def autolayout(session: AsyncSession, diagram: Diagram) -> Diagram:
    nodes = await _nodes(session, diagram.id)
    roles = await _roles(session, [node.ci_id for node in nodes if node.ci_id])
    types = await _ci_types(session, [node.ci_id for node in nodes if node.ci_id])
    positions = layered_layout(
        [
            (node.id, types.get(node.ci_id) if node.ci_id else None,
             roles.get(node.ci_id) if node.ci_id else None)
            for node in nodes
        ]
    )
    for node in nodes:
        x, y = positions[node.id]
        node.x = x
        node.y = y
    diagram.version += 1
    await session.flush()
    return diagram


async def sync_edges(session: AsyncSession, diagram: Diagram) -> int:
    """Добавляет рёбра для кабелей и связей, которых на схеме ещё нет.

    Удалённый кабель исчезает сам: ребро ссылается на него и каскадно удаляется.
    """
    nodes = await _nodes(session, diagram.id)
    by_ci = {node.ci_id: node for node in nodes if node.ci_id}
    if len(by_ci) < 2:
        return 0
    present = (
        await session.execute(
            select(DiagramEdge.connection_id, DiagramEdge.relation_id).where(
                DiagramEdge.diagram_id == diagram.id
            )
        )
    ).all()
    created = 0
    if diagram.diagram_type == DiagramType.NETWORK:
        taken = {row[0] for row in present if row[0] is not None}
        created += await _sync_cables(session, diagram.id, by_ci, taken)
    else:
        taken = {row[1] for row in present if row[1] is not None}
        created += await _sync_relations(session, diagram.id, by_ci, taken)
    if created:
        diagram.version += 1
        await session.flush()
    return created


async def _sync_cables(
    session: AsyncSession,
    diagram_id: uuid.UUID,
    by_ci: dict[uuid.UUID, DiagramNode],
    taken: set[Any],
) -> int:
    side_a = aliased(Interface)
    side_b = aliased(Interface)
    rows = await session.execute(
        select(Connection.id, side_a.ci_id, side_b.ci_id)
        .join(side_a, side_a.id == Connection.a_interface_id)
        .join(side_b, side_b.id == Connection.b_interface_id)
        .where(
            Connection.status.in_(ACTIVE_CABLE),
            side_a.ci_id.in_(by_ci),
            side_b.ci_id.in_(by_ci),
        )
    )
    created = 0
    for connection_id, ci_a, ci_b in rows:
        if connection_id in taken or ci_a not in by_ci or ci_b not in by_ci:
            continue
        session.add(
            DiagramEdge(
                diagram_id=diagram_id,
                connection_id=connection_id,
                source_node_id=by_ci[ci_a].id,
                target_node_id=by_ci[ci_b].id,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def _sync_relations(
    session: AsyncSession,
    diagram_id: uuid.UUID,
    by_ci: dict[uuid.UUID, DiagramNode],
    taken: set[Any],
) -> int:
    rows = await session.execute(
        select(CiRelation.id, CiRelation.source_ci_id, CiRelation.target_ci_id).where(
            CiRelation.source_ci_id.in_(by_ci),
            CiRelation.target_ci_id.in_(by_ci),
        )
    )
    created = 0
    for relation_id, source_id, target_id in rows:
        if relation_id in taken:
            continue
        session.add(
            DiagramEdge(
                diagram_id=diagram_id,
                relation_id=relation_id,
                source_node_id=by_ci[source_id].id,
                target_node_id=by_ci[target_id].id,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created


async def add_node(
    session: AsyncSession, diagram_id: uuid.UUID, ci_id: uuid.UUID
) -> DiagramNode:
    diagram = await get_diagram(session, diagram_id)
    ci = await session.get(Ci, ci_id)
    if ci is None or ci.deleted_at is not None:
        raise NotFound("Объект не найден", entity_id=str(ci_id))
    existing = (
        await session.execute(
            select(DiagramNode).where(
                DiagramNode.diagram_id == diagram_id, DiagramNode.ci_id == ci_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    nodes = await _nodes(session, diagram_id)
    node = DiagramNode(
        diagram_id=diagram_id,
        ci_id=ci_id,
        node_kind=DiagramNodeKind.CI,
        x=(len(nodes) % 4) * 280,
        y=(len(nodes) // 4) * 170,
        label=ci.name,
    )
    session.add(node)
    await session.flush()
    await sync_edges(session, diagram)
    return node


async def remove_node(session: AsyncSession, node_id: uuid.UUID) -> None:
    node = await session.get(DiagramNode, node_id)
    if node is None:
        raise NotFound("Узел схемы не найден", entity_id=str(node_id))
    diagram = await get_diagram(session, node.diagram_id)
    await session.delete(node)
    diagram.version += 1
    await session.flush()


async def save_layout(
    session: AsyncSession,
    diagram_id: uuid.UUID,
    version: int,
    nodes: list[dict[str, Any]],
    viewport: dict[str, Any] | None,
) -> Diagram:
    diagram = await get_diagram(session, diagram_id)
    if diagram.version != version:
        raise Conflict(
            "Схему уже изменили. Обновите страницу и повторите сохранение",
            code_hint="version_conflict",
        )
    by_id = {node.id: node for node in await _nodes(session, diagram_id)}
    for item in nodes:
        node = by_id.get(uuid.UUID(str(item["id"])))
        if node is None:
            raise NotFound("Узел схемы не найден", entity_id=str(item["id"]))
        node.x = item["x"]
        node.y = item["y"]
    if viewport is not None:
        diagram.viewport = viewport
    diagram.version += 1
    await session.flush()
    return diagram


async def _roles(session: AsyncSession, ci_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ci_ids:
        return {}
    rows = await session.execute(
        select(Device.id, Device.device_role).where(Device.id.in_(ci_ids))
    )
    return {ci_id: role.value if hasattr(role, "value") else str(role) for ci_id, role in rows}


async def _ci_types(session: AsyncSession, ci_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ci_ids:
        return {}
    rows = await session.execute(select(Ci.id, Ci.ci_type).where(Ci.id.in_(ci_ids)))
    return {ci_id: value.value if hasattr(value, "value") else str(value) for ci_id, value in rows}


async def full_diagram(session: AsyncSession, diagram_id: uuid.UUID) -> dict[str, Any]:
    """Узлы, рёбра и актуальные свойства объектов одним ответом."""
    diagram = await get_diagram(session, diagram_id)
    nodes = await _nodes(session, diagram.id)
    ci_ids = [node.ci_id for node in nodes if node.ci_id]
    ci_rows = {}
    if ci_ids:
        for ci in (await session.execute(select(Ci).where(Ci.id.in_(ci_ids)))).scalars():
            ci_rows[ci.id] = ci
    roles = await _roles(session, ci_ids)
    devices = {}
    if ci_ids:
        for device in (
            await session.execute(select(Device).where(Device.id.in_(ci_ids)))
        ).scalars():
            devices[device.id] = device

    edges = list(
        (
            await session.execute(
                select(DiagramEdge).where(DiagramEdge.diagram_id == diagram.id)
            )
        ).scalars()
    )
    cable_ids = [edge.connection_id for edge in edges if edge.connection_id]
    cables = await _cable_facts(session, cable_ids)
    relations = await _relation_facts(
        session, [edge.relation_id for edge in edges if edge.relation_id]
    )

    return {
        "diagram": diagram,
        "nodes": [
            _node_payload(node, ci_rows.get(node.ci_id) if node.ci_id else None,
                          devices.get(node.ci_id) if node.ci_id else None, roles)
            for node in nodes
        ],
        "edges": [_edge_payload(edge, cables, relations) for edge in edges],
    }


def _node_payload(
    node: DiagramNode, ci: Ci | None, device: Device | None, roles: dict[uuid.UUID, str]
) -> dict[str, Any]:
    return {
        "id": node.id,
        "ci_id": node.ci_id,
        "node_kind": node.node_kind,
        "x": float(node.x),
        "y": float(node.y),
        "label": (ci.name if ci else None) or node.label or "—",
        "code": ci.code if ci else None,
        "ci_type": ci.ci_type if ci else None,
        "status": ci.status if ci else None,
        "criticality": ci.criticality if ci else None,
        "device_role": roles.get(node.ci_id) if node.ci_id else None,
        "hostname": device.hostname if device else None,
        "mgmt_ip": str(device.mgmt_ip) if device and device.mgmt_ip else None,
    }


async def _cable_facts(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, Connection]:
    if not ids:
        return {}
    rows = await session.execute(select(Connection).where(Connection.id.in_(ids)))
    return {item.id: item for item in rows.scalars()}


async def _relation_facts(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, CiRelation]:
    if not ids:
        return {}
    rows = await session.execute(select(CiRelation).where(CiRelation.id.in_(ids)))
    return {item.id: item for item in rows.scalars()}


def _edge_payload(
    edge: DiagramEdge,
    cables: dict[uuid.UUID, Connection],
    relations: dict[uuid.UUID, CiRelation],
) -> dict[str, Any]:
    cable = cables.get(edge.connection_id) if edge.connection_id else None
    relation = relations.get(edge.relation_id) if edge.relation_id else None
    return {
        "id": edge.id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "connection_id": edge.connection_id,
        "relation_id": edge.relation_id,
        "label": cable.label if cable else (relation.rel_type if relation else None),
        "medium": cable.medium if cable else None,
        "status": cable.status if cable else None,
        "length_m": float(cable.length_m) if cable and cable.length_m is not None else None,
        "is_redundant": bool(cable.is_redundant) if cable else False,
        "redundancy_group": cable.redundancy_group if cable else None,
        "rel_type": relation.rel_type if relation else None,
    }
