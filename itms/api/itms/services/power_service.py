"""Питание: граф узлов, замеры и прогноз прироста относительно текущего ввода."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Invalid, NotFound
from itms.domain.power import (
    MEASUREMENT_TTL_DAYS,
    Addition,
    LoadLink,
    LoadNode,
    calculate,
    ensure_power_acyclic,
    forecast,
)
from itms.models.cmdb import Ci
from itms.models.enums import (
    MEASUREMENT_SOURCES,
    CiStatus,
    CiType,
    FeedSide,
    PhaseLabel,
    PowerNodeType,
)
from itms.models.network import Device
from itms.models.power import (
    PowerFeed,
    PowerLink,
    PowerMeasurement,
    PowerNode,
    PowerScenario,
    PowerScenarioItem,
)
from itms.models.projects import Project
from itms.services import ci_service

TYPE_ORDER = {item.value: index for index, item in enumerate(PowerNodeType)}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _enum(cls: type, value: Any) -> Any:
    if value is None or isinstance(value, cls):
        return value
    return cls(value)


async def _node_or_404(session: AsyncSession, node_id: uuid.UUID) -> PowerNode:
    node = await session.get(PowerNode, node_id)
    if node is None:
        raise NotFound("Узел питания не найден", entity_id=str(node_id))
    return node


def _validate_phase(node_type: PowerNodeType, phases: int, phase_label: PhaseLabel | None) -> None:
    if phases not in (1, 3):
        raise Invalid("Число фаз — 1 или 3", code_hint="phases")
    needs_phase = node_type not in {PowerNodeType.INPUT, PowerNodeType.PANEL}
    if phases == 1 and needs_phase and phase_label is None:
        raise Invalid(
            "Однофазный потребитель должен иметь фазу L1, L2 или L3",
            code_hint="phase_label_required",
        )


async def create_node(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    node_type = _enum(PowerNodeType, data["node_type"])
    phases = int(data.get("phases") or 1)
    phase_label = _enum(PhaseLabel, data.get("phase_label"))
    _validate_phase(node_type, phases, phase_label)
    ci = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.POWER_NODE,
            "name": data["name"].strip(),
            "code": data.get("code"),
            "location_id": data.get("location_id"),
            "description": data.get("description"),
            "status": CiStatus.ACTIVE,
        },
    )
    node = PowerNode(
        id=ci.id,
        node_type=node_type,
        parent_device_id=data.get("parent_device_id"),
        rack_id=data.get("rack_id"),
        feed_side=_enum(FeedSide, data.get("feed_side") or FeedSide.SINGLE),
        voltage_v=data.get("voltage_v"),
        phases=phases,
        phase_label=phase_label,
        rated_current_a=data.get("rated_current_a"),
        derating_factor=data.get("derating_factor", 0.8),
        power_factor=data.get("power_factor"),
        efficiency=data.get("efficiency"),
        power_nameplate_w=data.get("power_nameplate_w"),
        power_max_w=data.get("power_max_w"),
        max_load_w=data.get("max_load_w"),
        ups_capacity_va=data.get("ups_capacity_va"),
        ups_capacity_w=data.get("ups_capacity_w"),
        utilization=data.get("utilization"),
        notes=data.get("notes"),
    )
    session.add(node)
    await session.flush()
    return {"id": ci.id, "code": ci.code, "name": ci.name}


async def create_link(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    source_id = data["source_node_id"]
    target_id = data["target_node_id"]
    await _node_or_404(session, source_id)
    await _node_or_404(session, target_id)
    rows = (await session.execute(select(PowerLink.source_node_id, PowerLink.target_node_id))).all()
    edges: dict[str, list[str]] = {}
    for source, target in rows:
        edges.setdefault(str(source), []).append(str(target))
    ensure_power_acyclic(edges, str(source_id), str(target_id))
    link = PowerLink(source_node_id=source_id, target_node_id=target_id)
    session.add(link)
    await session.flush()
    return {"id": link.id, "source_node_id": source_id, "target_node_id": target_id}


async def create_feed(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    root = await _node_or_404(session, data["root_node_id"])
    side = _enum(FeedSide, data["side"])
    feed = PowerFeed(
        name=data["name"].strip(),
        side=side,
        root_node_id=root.id,
        location_id=data.get("location_id"),
        is_protected=bool(data.get("is_protected", False)),
        description=data.get("description") or "",
    )
    session.add(feed)
    await session.flush()
    if root.feed_id is None:
        root.feed_id = feed.id
        root.feed_side = side
        await session.flush()
    return {"id": feed.id, "name": feed.name, "side": side.value}


async def assign_feed(
    session: AsyncSession, node_id: uuid.UUID, feed_id: uuid.UUID, feed_side: FeedSide | str
) -> None:
    node = await _node_or_404(session, node_id)
    feed = await session.get(PowerFeed, feed_id)
    if feed is None:
        raise NotFound("Ветка питания не найдена", entity_id=str(feed_id))
    node.feed_id = feed.id
    node.feed_side = _enum(FeedSide, feed_side)
    await session.flush()


async def create_measurement(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    await _node_or_404(session, data["node_id"])
    source = data.get("source") or "MANUAL"
    if source not in MEASUREMENT_SOURCES:
        raise Invalid("Неизвестный источник замера", code_hint="measurement_source")
    measured_at = data.get("measured_at") or datetime.now(UTC)
    row = PowerMeasurement(
        node_id=data["node_id"],
        measured_at=measured_at,
        power_w=data.get("power_w"),
        current_a=data.get("current_a"),
        voltage_v=data.get("voltage_v"),
        power_factor=data.get("power_factor"),
        phase_label=_enum(PhaseLabel, data.get("phase_label")),
        source=source,
        instrument=data.get("instrument"),
        note=data.get("note") or "",
        is_peak=bool(data.get("is_peak", False)),
    )
    session.add(row)
    await session.flush()
    return {"id": row.id, "node_id": row.node_id, "power_w": row.power_w}


async def create_scenario(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    project_id = data.get("project_id")
    if project_id is not None and await session.get(Project, project_id) is None:
        raise NotFound("Проект не найден", entity_id=str(project_id))
    efficiency = data.get("ups_efficiency")
    if efficiency is not None and not 0 < float(efficiency) < 1:
        raise Invalid("КПД нового UPS должен быть между 0 и 1", code_hint="efficiency")
    scenario = PowerScenario(
        project_id=project_id,
        name=data["name"].strip(),
        description=data.get("description") or "",
        charge_w=int(data.get("charge_w") or 0),
        ups_efficiency=efficiency,
        reserve=data.get("reserve", 0.2),
    )
    session.add(scenario)
    await session.flush()
    for item in data.get("items") or []:
        session.add(
            PowerScenarioItem(
                scenario_id=scenario.id,
                name=item["name"].strip(),
                nameplate_w=int(item["nameplate_w"]),
                quantity=int(item.get("quantity") or 1),
                utilization=float(item["utilization"]),
                behind_new_ups=bool(item.get("behind_new_ups", True)),
            )
        )
    await session.flush()
    return {"id": scenario.id, "name": scenario.name}


def _latest(
    rows: list[PowerMeasurement], now: datetime
) -> dict[uuid.UUID, tuple[PowerMeasurement, bool, bool]]:
    latest: dict[uuid.UUID, PowerMeasurement] = {}
    for row in rows:
        current = latest.get(row.node_id)
        if current is None or row.measured_at > current.measured_at:
            latest[row.node_id] = row
    horizon = now - timedelta(days=MEASUREMENT_TTL_DAYS)
    result: dict[uuid.UUID, tuple[PowerMeasurement, bool, bool]] = {}
    for node_id, row in latest.items():
        fresh = row.measured_at >= horizon and row.power_w is not None
        stale = row.power_w is not None and not fresh
        result[node_id] = (row, fresh, stale)
    return result


def _load_node(
    node: PowerNode,
    ci: Ci,
    role: str | None,
    measurement: tuple[PowerMeasurement, bool, bool] | None,
) -> LoadNode:
    measured_w = None
    fresh = False
    stale = False
    if measurement is not None:
        row, fresh, stale = measurement
        measured_w = row.power_w
    return LoadNode(
        id=str(node.id),
        name=ci.name,
        node_type=node.node_type.value,
        phases=node.phases,
        phase_label=node.phase_label.value if node.phase_label else None,
        voltage_v=_num(node.voltage_v),
        rated_current_a=_num(node.rated_current_a),
        derating_factor=_num(node.derating_factor) or 0.8,
        power_factor=_num(node.power_factor),
        efficiency=_num(node.efficiency),
        nameplate_w=node.power_nameplate_w,
        peak_w=node.power_max_w,
        max_load_w=node.max_load_w,
        ups_capacity_va=node.ups_capacity_va,
        ups_capacity_w=node.ups_capacity_w,
        feed_id=str(node.feed_id) if node.feed_id else None,
        feed_side=node.feed_side.value,
        parent_device_id=str(node.parent_device_id) if node.parent_device_id else None,
        utilization=_num(node.utilization),
        device_role=role,
        measured_w=measured_w,
        measurement_fresh=fresh,
        measurement_stale=stale,
    )


async def overview(session: AsyncSession) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(PowerNode, Ci)
            .join(Ci, Ci.id == PowerNode.id)
            .where(Ci.deleted_at.is_(None))
            .order_by(Ci.name)
        )
    ).all()
    links = list((await session.execute(select(PowerLink))).scalars())
    feeds = list((await session.execute(select(PowerFeed).order_by(PowerFeed.name))).scalars())
    measurements = list((await session.execute(select(PowerMeasurement))).scalars())
    parent_ids = [node.parent_device_id for node, _ in rows if node.parent_device_id]
    roles: dict[uuid.UUID, str] = {}
    if parent_ids:
        devices = (await session.execute(select(Device).where(Device.id.in_(parent_ids)))).scalars()
        roles = {device.id: device.device_role.value for device in devices}
    fresh = _latest(measurements, datetime.now(UTC))
    load_nodes = []
    for node, ci in rows:
        role = roles.get(node.parent_device_id) if node.parent_device_id else None
        load_nodes.append(_load_node(node, ci, role, fresh.get(node.id)))
    report = calculate(
        load_nodes,
        [LoadLink(str(link.source_node_id), str(link.target_node_id)) for link in links],
    )
    feed_by_id = {feed.id: feed for feed in feeds}
    ci_by_id = {ci.id: ci for _, ci in rows}
    node_by_id = {node.id: node for node, _ in rows}
    payloads = []
    for node, ci in rows:
        result = report.nodes[str(node.id)]
        feed = feed_by_id.get(node.feed_id) if node.feed_id else None
        payloads.append(
            {
                "id": node.id,
                "code": ci.code,
                "name": ci.name,
                "node_type": node.node_type.value,
                "feed_id": node.feed_id,
                "feed_name": feed.name if feed else None,
                "feed_side": node.feed_side.value,
                "nameplate_w": result.nameplate_w,
                "estimated_w": result.estimated_w,
                "inlet_w": result.inlet_w,
                "used_w": result.used_w,
                "limit_w": result.limit_w,
                "headroom_w": result.headroom_w,
                "current_a": result.current_a,
                "disbalance_pct": result.disbalance_pct,
                "phases_w": result.phases_w,
                "value_source": result.value_source,
                "measured_coverage_pct": result.measured_coverage_pct,
                "warnings": result.warnings,
                "trace": result.trace,
                "failover": result.failover,
                "failover_detail": result.failover_detail,
                "estimated_with_charge_w": result.estimated_with_charge_w,
            }
        )
    payloads.sort(key=lambda row: (TYPE_ORDER.get(row["node_type"], 99), row["name"]))
    inputs = [row for row in payloads if row["node_type"] == "INPUT"]
    primary = max(inputs, key=lambda row: (row["inlet_w"], row["code"] or "")) if inputs else None
    scenarios = await _scenarios(session, primary)
    return {
        "nodes": payloads,
        "feeds": [
            {
                "id": feed.id,
                "name": feed.name,
                "side": feed.side.value,
                "root_node_id": feed.root_node_id,
                "root_name": ci_by_id[feed.root_node_id].name
                if feed.root_node_id in ci_by_id
                else None,
                "is_protected": feed.is_protected,
                "description": feed.description,
            }
            for feed in feeds
        ],
        "primary_input_id": primary["id"] if primary else None,
        "scenarios": scenarios,
        "links": [
            {
                "id": link.id,
                "source_node_id": link.source_node_id,
                "target_node_id": link.target_node_id,
                "source_name": ci_by_id[link.source_node_id].name
                if link.source_node_id in ci_by_id
                else None,
                "target_name": ci_by_id[link.target_node_id].name
                if link.target_node_id in ci_by_id
                else None,
            }
            for link in links
            if link.source_node_id in node_by_id and link.target_node_id in node_by_id
        ],
    }


async def _scenarios(session: AsyncSession, primary: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = list(
        (await session.execute(select(PowerScenario).order_by(PowerScenario.name))).scalars()
    )
    if not rows:
        return []
    items = list((await session.execute(select(PowerScenarioItem))).scalars())
    by_scenario: dict[uuid.UUID, list[PowerScenarioItem]] = {}
    for item in items:
        by_scenario.setdefault(item.scenario_id, []).append(item)
    project_ids = [row.project_id for row in rows if row.project_id]
    projects: dict[uuid.UUID, Project] = {}
    if project_ids:
        found = (
            await session.execute(select(Project).where(Project.id.in_(project_ids)))
        ).scalars()
        projects = {project.id: project for project in found}
    result = []
    for row in rows:
        scenario_items = by_scenario.get(row.id, [])
        additions = [
            Addition(
                name=item.name,
                nameplate_w=item.nameplate_w,
                quantity=item.quantity,
                utilization=float(item.utilization),
                behind_new_ups=item.behind_new_ups,
            )
            for item in scenario_items
        ]
        numbers = None
        if primary is not None and primary.get("limit_w") is not None:
            numbers = forecast(
                current_estimated_w=primary["inlet_w"],
                current_nameplate_w=primary["nameplate_w"],
                input_limit_w=primary["limit_w"],
                additions=additions,
                ups_efficiency=_num(row.ups_efficiency),
                charge_w=row.charge_w,
                reserve=float(row.reserve),
            )
        project = projects.get(row.project_id) if row.project_id else None
        result.append(
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "project_id": row.project_id,
                "project_key": project.key if project else None,
                "charge_w": row.charge_w,
                "ups_efficiency": _num(row.ups_efficiency),
                "reserve": float(row.reserve),
                "items": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "nameplate_w": item.nameplate_w,
                        "quantity": item.quantity,
                        "utilization": float(item.utilization),
                        "behind_new_ups": item.behind_new_ups,
                    }
                    for item in scenario_items
                ],
                "forecast": numbers,
            }
        )
    return result
