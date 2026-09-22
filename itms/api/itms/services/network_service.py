"""Интерфейсы, кабели, трассы и сквозная трассировка линков."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.network import (
    InterfaceFacts,
    LinkSegment,
    normalize_mac,
    redundancy_violations,
    trace_link,
    validate_connection,
)
from itms.models.cmdb import Ci
from itms.models.enums import (
    LOGICAL_INTERFACE_TYPES,
    OCCUPYING_CONNECTION_STATUSES,
    CableMedium,
    ConnectionStatus,
    InterfaceType,
    VlanMode,
)
from itms.models.network import (
    CableRoute,
    Connection,
    Device,
    Interface,
    InterfaceVlan,
    IpAddress,
    Vlan,
)
from itms.services import ci_service

INTERFACE_FIELDS = (
    "name",
    "position",
    "interface_type",
    "medium",
    "speed_mbps",
    "duplex",
    "mac",
    "description",
    "purpose",
    "admin_enabled",
    "oper_status",
    "is_management",
    "poe_mode",
    "mtu",
    "lag_parent_id",
    "panel_side",
    "paired_interface_id",
)
CONNECTION_FIELDS = (
    "label",
    "medium",
    "category",
    "connector_a",
    "connector_b",
    "length_m",
    "speed_mbps",
    "color",
    "status",
    "route_id",
    "is_redundant",
    "redundancy_group",
    "installed_on",
    "tested_on",
    "test_result",
    "description",
)
ROUTE_FIELDS = ("name", "route_type", "from_location_id", "to_location_id", "length_m",
                "capacity", "notes")


# --- Интерфейсы ---------------------------------------------------------------


async def get_interface(session: AsyncSession, interface_id: uuid.UUID) -> Interface:
    interface = (
        await session.execute(
            select(Interface)
            .options(selectinload(Interface.vlans).selectinload(InterfaceVlan.vlan))
            .where(Interface.id == interface_id)
        )
    ).scalars().unique().one_or_none()
    if interface is None:
        raise NotFound("Интерфейс не найден", entity_id=str(interface_id))
    return interface


async def occupied_interface_ids(
    session: AsyncSession, interface_ids: list[uuid.UUID] | None = None
) -> set[uuid.UUID]:
    """Порты, на которых висит кабель в занимающем статусе."""
    stmt = select(Connection.a_interface_id, Connection.b_interface_id).where(
        Connection.status.in_(tuple(OCCUPYING_CONNECTION_STATUSES))
    )
    if interface_ids:
        stmt = stmt.where(
            or_(
                Connection.a_interface_id.in_(interface_ids),
                Connection.b_interface_id.in_(interface_ids),
            )
        )
    result: set[uuid.UUID] = set()
    for a_id, b_id in await session.execute(stmt):
        result.add(a_id)
        result.add(b_id)
    return result


async def list_interfaces(session: AsyncSession, ci_id: uuid.UUID) -> list[dict[str, Any]]:
    interfaces = list(
        (
            await session.execute(
                select(Interface)
                .options(selectinload(Interface.vlans).selectinload(InterfaceVlan.vlan))
                .where(Interface.ci_id == ci_id)
                .order_by(Interface.position.nulls_last(), Interface.name)
            )
        ).scalars().unique()
    )
    if not interfaces:
        return []
    ids = [i.id for i in interfaces]
    connections = list(
        (
            await session.execute(
                select(Connection).where(
                    or_(
                        Connection.a_interface_id.in_(ids),
                        Connection.b_interface_id.in_(ids),
                    )
                )
            )
        ).scalars().unique()
    )
    by_interface: dict[uuid.UUID, Connection] = {}
    for connection in connections:
        for side in (connection.a_interface_id, connection.b_interface_id):
            if side in ids and (
                side not in by_interface
                or connection.status in OCCUPYING_CONNECTION_STATUSES
            ):
                by_interface[side] = connection

    addresses: dict[uuid.UUID, list[str]] = defaultdict(list)
    for interface_id, address in await session.execute(
        select(IpAddress.interface_id, IpAddress.address).where(IpAddress.interface_id.in_(ids))
    ):
        addresses[interface_id].append(str(address))

    peers = await _peer_labels(session, connections, ids)
    return [
        {
            "id": interface.id,
            "ci_id": interface.ci_id,
            "name": interface.name,
            "position": interface.position,
            "interface_type": interface.interface_type,
            "medium": interface.medium,
            "speed_mbps": interface.speed_mbps,
            "mac": interface.mac,
            "description": interface.description,
            "purpose": interface.purpose,
            "admin_enabled": interface.admin_enabled,
            "oper_status": interface.oper_status,
            "is_management": interface.is_management,
            "mtu": interface.mtu,
            "panel_side": interface.panel_side,
            "paired_interface_id": interface.paired_interface_id,
            "lag_parent_id": interface.lag_parent_id,
            "ip_addresses": addresses.get(interface.id, []),
            "vlans": [
                {"vlan_id": link.vlan_id, "vid": link.vlan.vid, "name": link.vlan.name,
                 "mode": link.mode}
                for link in interface.vlans
            ],
            "connection": _connection_brief(by_interface.get(interface.id), interface.id, peers),
        }
        for interface in interfaces
    ]


async def _peer_labels(
    session: AsyncSession, connections: list[Connection], own_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Подписи дальних концов: «SW-CORE-01 / Te1/0/49» без второго запроса на строку."""
    peer_ids = {
        (c.b_interface_id if c.a_interface_id in own_ids else c.a_interface_id)
        for c in connections
    }
    if not peer_ids:
        return {}
    rows = await session.execute(
        select(Interface.id, Interface.name, Ci.id, Ci.name)
        .join(Ci, Ci.id == Interface.ci_id)
        .where(Interface.id.in_(peer_ids))
    )
    return {
        interface_id: {
            "interface_id": interface_id,
            "interface_name": interface_name,
            "ci_id": ci_id,
            "ci_name": ci_name,
        }
        for interface_id, interface_name, ci_id, ci_name in rows
    }


def _connection_brief(
    connection: Connection | None,
    interface_id: uuid.UUID,
    peers: dict[uuid.UUID, dict[str, Any]],
) -> dict[str, Any] | None:
    if connection is None:
        return None
    far_end = (
        connection.b_interface_id
        if connection.a_interface_id == interface_id
        else connection.a_interface_id
    )
    return {
        "id": connection.id,
        "label": connection.label,
        "status": connection.status,
        "medium": connection.medium,
        "length_m": float(connection.length_m) if connection.length_m is not None else None,
        "peer": peers.get(far_end),
    }


async def create_interface(
    session: AsyncSession, ci_id: uuid.UUID, data: dict[str, Any]
) -> Interface:
    await ci_service.get_ci(session, ci_id)
    payload = {k: v for k, v in data.items() if k in INTERFACE_FIELDS}
    payload["mac"] = normalize_mac(payload.get("mac"))
    duplicate = (
        await session.execute(
            select(Interface.id).where(
                Interface.ci_id == ci_id, Interface.name == payload["name"]
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict(f"Порт «{payload['name']}» у объекта уже есть", field="name")
    vlans = data.get("vlans")
    interface = Interface(ci_id=ci_id, **payload)
    session.add(interface)
    await session.flush()
    if vlans:
        await set_interface_vlans(session, interface.id, vlans)
    await _reindex_owner(session, ci_id)
    return await get_interface(session, interface.id)


async def update_interface(
    session: AsyncSession, interface_id: uuid.UUID, data: dict[str, Any]
) -> Interface:
    interface = await get_interface(session, interface_id)
    payload = {k: v for k, v in data.items() if k in INTERFACE_FIELDS}
    if "mac" in payload:
        payload["mac"] = normalize_mac(payload["mac"])
    if "paired_interface_id" in payload and payload["paired_interface_id"] == interface_id:
        raise Invalid("Порт не может быть сопряжён сам с собой", code_hint="self_pairing")
    for field, value in payload.items():
        setattr(interface, field, value)
    if "vlans" in data:
        await set_interface_vlans(session, interface_id, data["vlans"] or [])
    await session.flush()
    await _reindex_owner(session, interface.ci_id)
    return await get_interface(session, interface_id)


async def delete_interface(session: AsyncSession, interface_id: uuid.UUID) -> None:
    interface = await get_interface(session, interface_id)
    occupied = await occupied_interface_ids(session, [interface_id])
    if interface_id in occupied:
        raise Conflict("Сначала снимите кабель с порта", code_hint="port_occupied")
    ci_id = interface.ci_id
    await session.delete(interface)
    await session.flush()
    await _reindex_owner(session, ci_id)


async def set_interface_vlans(
    session: AsyncSession, interface_id: uuid.UUID, vlans: list[dict[str, Any]]
) -> None:
    existing = {
        link.vlan_id: link
        for link in (
            await session.execute(
                select(InterfaceVlan).where(InterfaceVlan.interface_id == interface_id)
            )
        ).scalars()
    }
    wanted = {uuid.UUID(str(item["vlan_id"])): VlanMode(item["mode"]) for item in vlans}
    for vlan_id in set(existing) - set(wanted):
        await session.delete(existing[vlan_id])
    for vlan_id, mode in wanted.items():
        if vlan_id in existing:
            existing[vlan_id].mode = mode
            continue
        if await session.get(Vlan, vlan_id) is None:
            raise NotFound("VLAN не найден", entity_id=str(vlan_id))
        session.add(InterfaceVlan(interface_id=interface_id, vlan_id=vlan_id, mode=mode))
    natives = [mode for mode in wanted.values() if mode == VlanMode.NATIVE]
    if len(natives) > 1:
        raise Invalid("У порта может быть только один native VLAN", code_hint="many_native_vlans")
    await session.flush()


async def _reindex_owner(session: AsyncSession, ci_id: uuid.UUID) -> None:
    from itms.services import device_service

    if await session.get(Device, ci_id) is not None:
        await device_service.reindex_device(session, ci_id)


# --- Кабели -------------------------------------------------------------------


async def _facts(session: AsyncSession, interface_id: uuid.UUID) -> InterfaceFacts:
    row = (
        await session.execute(
            select(Interface, Device.device_role)
            .outerjoin(Device, Device.id == Interface.ci_id)
            .where(Interface.id == interface_id)
        )
    ).first()
    if row is None:
        raise NotFound("Интерфейс не найден", entity_id=str(interface_id))
    interface, role = row
    occupied = interface_id in await occupied_interface_ids(session, [interface_id])
    return InterfaceFacts(
        id=interface.id,
        ci_id=interface.ci_id,
        name=interface.name,
        interface_type=InterfaceType(interface.interface_type),
        medium=CableMedium(interface.medium) if interface.medium else None,
        speed_mbps=interface.speed_mbps,
        device_role=role,
        paired_interface_id=interface.paired_interface_id,
        occupied=occupied,
    )


async def create_connection(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    side_a = await _facts(session, uuid.UUID(str(data["a_interface_id"])))
    side_b = await _facts(session, uuid.UUID(str(data["b_interface_id"])))
    status = ConnectionStatus(data.get("status", ConnectionStatus.ACTIVE))
    medium = CableMedium(data["medium"])
    check = validate_connection(
        side_a,
        side_b,
        medium=medium,
        speed_mbps=data.get("speed_mbps"),
        occupies_port=status in OCCUPYING_CONNECTION_STATUSES,
    )
    connection = Connection(
        a_interface_id=side_a.id,
        b_interface_id=side_b.id,
        **{k: v for k, v in data.items() if k in CONNECTION_FIELDS and k != "medium"},
        medium=medium,
    )
    session.add(connection)
    await session.flush()
    await _reindex_owner(session, side_a.ci_id)
    await _reindex_owner(session, side_b.ci_id)
    return {
        "connection": await connection_detail(session, connection.id),
        "warnings": check.warnings,
    }


async def connection_detail(session: AsyncSession, connection_id: uuid.UUID) -> dict[str, Any]:
    connection = await get_connection(session, connection_id)
    endpoints = await _endpoint_labels(session, [connection])
    return _connection_row(connection, endpoints)


async def get_connection(session: AsyncSession, connection_id: uuid.UUID) -> Connection:
    connection = (
        await session.execute(select(Connection).where(Connection.id == connection_id))
    ).scalars().unique().one_or_none()
    if connection is None:
        raise NotFound("Кабель не найден", entity_id=str(connection_id))
    return connection


async def update_connection(
    session: AsyncSession, connection_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    connection = await get_connection(session, connection_id)
    warnings: list[str] = []
    if "status" in data and data["status"] is not None:
        new_status = ConnectionStatus(data["status"])
        if (
            new_status in OCCUPYING_CONNECTION_STATUSES
            and connection.status not in OCCUPYING_CONNECTION_STATUSES
        ):
            side_a = await _facts(session, connection.a_interface_id)
            side_b = await _facts(session, connection.b_interface_id)
            warnings = validate_connection(
                side_a, side_b, medium=CableMedium(connection.medium)
            ).warnings
    for field in CONNECTION_FIELDS:
        if field in data:
            setattr(connection, field, data[field])
    await session.flush()
    return {
        "connection": await connection_detail(session, connection_id),
        "warnings": warnings,
    }


async def delete_connection(session: AsyncSession, connection_id: uuid.UUID) -> None:
    connection = await get_connection(session, connection_id)
    await session.delete(connection)
    await session.flush()


async def list_connections(
    session: AsyncSession,
    ci_id: uuid.UUID | None = None,
    status: list[ConnectionStatus] | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Connection)
    if ci_id:
        owned = select(Interface.id).where(Interface.ci_id == ci_id)
        stmt = stmt.where(
            or_(Connection.a_interface_id.in_(owned), Connection.b_interface_id.in_(owned))
        )
    if status:
        stmt = stmt.where(Connection.status.in_(status))
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Connection.label).like(pattern),
                func.lower(Connection.redundancy_group).like(pattern),
            )
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = list(
        (
            await session.execute(stmt.order_by(Connection.label).limit(limit).offset(offset))
        ).scalars().unique()
    )
    endpoints = await _endpoint_labels(session, rows)
    return [_connection_row(connection, endpoints) for connection in rows], int(total)


async def _endpoint_labels(
    session: AsyncSession, connections: list[Connection]
) -> dict[uuid.UUID, dict[str, Any]]:
    ids = {c.a_interface_id for c in connections} | {c.b_interface_id for c in connections}
    if not ids:
        return {}
    rows = await session.execute(
        select(Interface.id, Interface.name, Ci.id, Ci.name)
        .join(Ci, Ci.id == Interface.ci_id)
        .where(Interface.id.in_(ids))
    )
    return {
        interface_id: {
            "interface_id": interface_id,
            "interface_name": interface_name,
            "ci_id": ci_id,
            "ci_name": ci_name,
        }
        for interface_id, interface_name, ci_id, ci_name in rows
    }


def _connection_row(
    connection: Connection, endpoints: dict[uuid.UUID, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": connection.id,
        "label": connection.label,
        "medium": connection.medium,
        "category": connection.category,
        "status": connection.status,
        "length_m": float(connection.length_m) if connection.length_m is not None else None,
        "speed_mbps": connection.speed_mbps,
        "color": connection.color,
        "is_redundant": connection.is_redundant,
        "redundancy_group": connection.redundancy_group,
        "route_id": connection.route_id,
        "installed_on": connection.installed_on,
        "description": connection.description,
        "a_end": endpoints.get(connection.a_interface_id),
        "b_end": endpoints.get(connection.b_interface_id),
    }


# --- Трассировка --------------------------------------------------------------


async def trace(session: AsyncSession, interface_id: uuid.UUID) -> dict[str, Any]:
    """Сквозной линк от порта: из каких кусков состоит и где реально заканчивается."""
    start = await _facts(session, interface_id)
    facts_cache: dict[uuid.UUID, InterfaceFacts | None] = {start.id: start}
    segment_cache: dict[uuid.UUID, LinkSegment | None] = {}

    interface_rows = await session.execute(
        select(Interface, Device.device_role).outerjoin(Device, Device.id == Interface.ci_id)
    )
    for interface, role in interface_rows:
        facts_cache[interface.id] = InterfaceFacts(
            id=interface.id,
            ci_id=interface.ci_id,
            name=interface.name,
            interface_type=InterfaceType(interface.interface_type),
            medium=CableMedium(interface.medium) if interface.medium else None,
            speed_mbps=interface.speed_mbps,
            device_role=role,
            paired_interface_id=interface.paired_interface_id,
        )
    for connection in (
        await session.execute(
            select(Connection).where(Connection.status == ConnectionStatus.ACTIVE)
        )
    ).scalars().unique():
        segment = LinkSegment(
            connection_id=connection.id,
            label=connection.label,
            length_m=float(connection.length_m) if connection.length_m is not None else None,
            from_interface_id=connection.a_interface_id,
            to_interface_id=connection.b_interface_id,
        )
        segment_cache[connection.a_interface_id] = segment
        segment_cache[connection.b_interface_id] = segment

    visited_segments: set[uuid.UUID] = set()

    def connection_of(current: uuid.UUID) -> LinkSegment | None:
        segment = segment_cache.get(current)
        if segment is None or segment.connection_id in visited_segments:
            return None
        visited_segments.add(segment.connection_id)
        return segment

    path = trace_link(start, connection_of, facts_cache.get)
    endpoint = facts_cache.get(path.endpoint_interface_id) if path.endpoint_interface_id else None
    names = await _endpoint_names(session, [start.ci_id, *path.passed_through,
                                            *( [endpoint.ci_id] if endpoint else [])])
    return {
        "start": {"interface_id": start.id, "interface_name": start.name,
                  "ci_id": start.ci_id, "ci_name": names.get(start.ci_id)},
        "endpoint": (
            {"interface_id": endpoint.id, "interface_name": endpoint.name,
             "ci_id": endpoint.ci_id, "ci_name": names.get(endpoint.ci_id)}
            if endpoint
            else None
        ),
        "segments": [
            {
                "connection_id": segment.connection_id,
                "label": segment.label,
                "length_m": segment.length_m,
            }
            for segment in path.segments
        ],
        "passed_through": [
            {"ci_id": ci_id, "ci_name": names.get(ci_id)} for ci_id in path.passed_through
        ],
        "total_length_m": path.total_length_m,
        "is_direct": path.is_direct,
        "truncated": path.truncated,
    }


async def _endpoint_names(
    session: AsyncSession, ci_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    unique = [ci_id for ci_id in dict.fromkeys(ci_ids) if ci_id]
    if not unique:
        return {}
    rows = await session.execute(select(Ci.id, Ci.name).where(Ci.id.in_(unique)))
    return dict(rows.all())  # type: ignore[arg-type]


async def redundancy_report(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.execute(
                select(Connection)
                .options(selectinload(Connection.route))
                .where(Connection.redundancy_group.isnot(None))
            )
        ).scalars().unique()
    )
    grouped: dict[str, list[Connection]] = defaultdict(list)
    for connection in rows:
        grouped[str(connection.redundancy_group)].append(connection)
    report: list[dict[str, Any]] = []
    for group, members in sorted(grouped.items()):
        issues = redundancy_violations(
            group,
            [
                (c.id, c.route.name if c.route else None, str(c.status))
                for c in members
            ],
        )
        report.append(
            {
                "group": group,
                "members": [{"id": c.id, "label": c.label, "status": c.status} for c in members],
                "issues": issues,
            }
        )
    return report


async def free_ports_report(session: AsyncSession) -> list[dict[str, Any]]:
    """Отчёт «свободные порты» по устройствам: прямое следствие модели."""
    taken = await occupied_interface_ids(session)
    rows = await session.execute(
        select(Ci.id, Ci.name, Device.device_role, Interface.id, Interface.interface_type)
        .join(Device, Device.id == Ci.id)
        .join(Interface, Interface.ci_id == Ci.id)
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .where(Interface.interface_type.notin_(tuple(LOGICAL_INTERFACE_TYPES)))
    )
    summary: dict[uuid.UUID, dict[str, Any]] = {}
    for ci_id, name, role, interface_id, _interface_type in rows:
        entry = summary.setdefault(
            ci_id, {"ci_id": ci_id, "name": name, "device_role": role, "total": 0, "free": 0}
        )
        entry["total"] += 1
        if interface_id not in taken:
            entry["free"] += 1
    return sorted(summary.values(), key=lambda item: (-item["free"], item["name"]))


# --- Трассы -------------------------------------------------------------------


async def list_routes(session: AsyncSession) -> list[CableRoute]:
    return list((await session.execute(select(CableRoute).order_by(CableRoute.name))).scalars())


async def create_route(session: AsyncSession, data: dict[str, Any]) -> CableRoute:
    duplicate = (
        await session.execute(select(CableRoute.id).where(CableRoute.name == data["name"]))
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict(f"Трасса «{data['name']}» уже есть", field="name")
    route = CableRoute(**{k: v for k, v in data.items() if k in ROUTE_FIELDS})
    session.add(route)
    await session.flush()
    return route
