"""Фиксация текущего питания и применение целевой схемы проекта."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.context import current_context
from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.transition import TARGET_PLAN_NAME, architecture_items, checksum, power_gap
from itms.models.cmdb import Ci
from itms.models.datacenter import Rack
from itms.models.floorplan import Floorplan, FloorplanItem
from itms.models.power import PowerLink, PowerNode
from itms.models.projects import Project
from itms.models.transition import ChangeItem, PlannedChange, StateSnapshot
from itms.services import floorplan_service, power_service, rack_service, search_service

_POWER_FIELDS = ("max_load_w", "rated_current_a", "voltage_v")


async def _project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFound("Проект не найден", entity_id=str(project_id))
    return project


def _scenario_for(overview: dict[str, Any], project_id: uuid.UUID) -> dict[str, Any] | None:
    for scenario in overview["scenarios"]:
        if scenario.get("project_id") == project_id:
            return scenario
    return None


def _primary(overview: dict[str, Any]) -> dict[str, Any] | None:
    primary_id = overview.get("primary_input_id")
    if primary_id is None:
        return None
    return next((node for node in overview["nodes"] if node["id"] == primary_id), None)


def _live(overview: dict[str, Any], project_id: uuid.UUID) -> dict[str, Any]:
    scenario = _scenario_for(overview, project_id)
    primary = _primary(overview)
    forecast = (scenario or {}).get("forecast") or {}
    return {
        "input_id": primary["id"] if primary else None,
        "input_name": primary["name"] if primary else None,
        "input_code": primary["code"] if primary else None,
        "estimated_w": primary["inlet_w"] if primary else None,
        "nameplate_w": primary["nameplate_w"] if primary else None,
        "limit_w": primary["limit_w"] if primary else None,
        "headroom_w": primary["headroom_w"] if primary else None,
        "target_w": forecast.get("target_estimated_w"),
        "deficit_w": forecast.get("deficit_w"),
        "required_w": forecast.get("required_input_w"),
        "recommended_w": forecast.get("recommended_3x50_w"),
        "added_w": forecast.get("added_estimated_w"),
    }


def _payload(overview: dict[str, Any], project_id: uuid.UUID) -> dict[str, Any]:
    live = _live(overview, project_id)
    scenario = _scenario_for(overview, project_id)
    return {
        "input": {
            "id": str(live["input_id"]) if live["input_id"] else None,
            "code": live["input_code"],
            "name": live["input_name"],
            "estimated_w": live["estimated_w"],
            "nameplate_w": live["nameplate_w"],
            "limit_w": live["limit_w"],
            "headroom_w": live["headroom_w"],
        },
        "forecast": (scenario or {}).get("forecast"),
        "nodes": [
            {
                "id": str(node["id"]),
                "code": node["code"],
                "name": node["name"],
                "node_type": node["node_type"],
                "inlet_w": node["inlet_w"],
                "limit_w": node["limit_w"],
            }
            for node in overview["nodes"]
        ],
    }


async def take_snapshot(session: AsyncSession, project_id: uuid.UUID, name: str) -> dict[str, Any]:
    await _project(session, project_id)
    title = name.strip()
    if not title:
        raise Invalid("У снимка должно быть имя", code_hint="invalid")
    overview = await power_service.overview(session)
    payload = _payload(overview, project_id)
    snapshot = StateSnapshot(
        project_id=project_id,
        name=title,
        scope={"include": ["power_node", "power_scenario"]},
        payload=payload,
        checksum=checksum(payload),
        taken_at=datetime.now(UTC),
        taken_by=current_context().actor_id,
    )
    session.add(snapshot)
    await session.flush()
    return _snapshot_row(snapshot)


async def build_plan(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    await _project(session, project_id)
    existing = (
        (
            await session.execute(
                select(PlannedChange).where(
                    PlannedChange.project_id == project_id,
                    PlannedChange.status != "CANCELLED",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return await view(session, project_id)
    overview = await power_service.overview(session)
    scenario = _scenario_for(overview, project_id)
    forecast = (scenario or {}).get("forecast") or {}
    primary = _primary(overview)
    if primary is None or not forecast:
        raise Invalid(
            "Для плана нужен ввод и прогноз нагрузки проекта",
            code_hint="power_plan_source",
        )
    node = await session.get(PowerNode, primary["id"])
    if node is None:
        raise NotFound("Узел ввода не найден", entity_id=str(primary["id"]))
    recommended = int(forecast["recommended_3x50_w"])
    latest = (
        (
            await session.execute(
                select(StateSnapshot)
                .where(StateSnapshot.project_id == project_id)
                .order_by(StateSnapshot.taken_at.desc())
            )
        )
        .scalars()
        .first()
    )
    plan = PlannedChange(
        project_id=project_id,
        name=TARGET_PLAN_NAME,
        base_snapshot_id=latest.id if latest else None,
        status="DRAFT",
    )
    session.add(plan)
    await session.flush()
    rated = float(node.rated_current_a) if node.rated_current_a is not None else None
    session.add(
        ChangeItem(
            planned_change_id=plan.id,
            operation="UPDATE",
            entity_type="power_node",
            entity_id=node.id,
            order_index=0,
            apply_status="PENDING",
            payload={
                "summary": "Ввод 3×32 А поднимается до 3×50 А",
                "fields": {"max_load_w": recommended, "rated_current_a": 50},
                "before": {"max_load_w": node.max_load_w, "rated_current_a": rated},
            },
        )
    )
    await session.flush()
    await _append_architecture(session, plan, overview, primary)
    return await view(session, project_id)


async def ensure_architecture(session: AsyncSession, project_id: uuid.UUID) -> None:
    """Дописывает стойку, UPS и PDU в уже собранный черновик. Модель не меняет."""
    plan = (
        (
            await session.execute(
                select(PlannedChange).where(
                    PlannedChange.project_id == project_id,
                    PlannedChange.status == "DRAFT",
                )
            )
        )
        .scalars()
        .first()
    )
    if plan is None:
        return
    overview = await power_service.overview(session)
    primary = _primary(overview)
    if primary is None:
        return
    await _append_architecture(session, plan, overview, primary)


async def apply_plan(
    session: AsyncSession, project_id: uuid.UUID, plan_id: uuid.UUID
) -> dict[str, Any]:
    plan = await _plan(session, project_id, plan_id)
    if plan.status == "APPLIED":
        raise Conflict("План уже применён", code_hint="already_applied")
    if plan.status == "CANCELLED":
        raise Conflict("Отменённый план не применяется", code_hint="cancelled")
    items = await _items(session, plan.id)
    refs: dict[str, uuid.UUID] = {}
    for item in items:
        await _apply_item(session, item, refs)
    plan.status = "APPLIED"
    plan.applied_at = datetime.now(UTC)
    await session.flush()
    snapshot = await take_snapshot(session, project_id, "После применения")
    plan.result_snapshot_id = snapshot["id"]
    await session.flush()
    return await view(session, project_id)


async def rollback_plan(
    session: AsyncSession, project_id: uuid.UUID, plan_id: uuid.UUID
) -> dict[str, Any]:
    plan = await _plan(session, project_id, plan_id)
    if plan.status != "APPLIED":
        raise Conflict("Откатывается только применённый план", code_hint="not_applied")
    items = await _items(session, plan.id)
    for item in reversed(items):
        await _restore_item(session, item)
    plan.status = "DRAFT"
    plan.applied_at = None
    await session.flush()
    await take_snapshot(session, project_id, "После отката")
    return await view(session, project_id)


async def view(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    await _project(session, project_id)
    overview = await power_service.overview(session)
    live = _live(overview, project_id)
    snapshots = list(
        (
            await session.execute(
                select(StateSnapshot)
                .where(StateSnapshot.project_id == project_id)
                .order_by(StateSnapshot.taken_at.desc())
            )
        ).scalars()
    )
    plans = list(
        (
            await session.execute(
                select(PlannedChange)
                .where(PlannedChange.project_id == project_id)
                .order_by(PlannedChange.name)
            )
        ).scalars()
    )
    plan_rows = []
    for plan in plans:
        items = await _items(session, plan.id)
        plan_rows.append(_plan_row(plan, items, live))
    active = next((row for row in plan_rows if row["status"] != "CANCELLED"), None)
    return {
        "live": live,
        "snapshots": [_snapshot_row(row) for row in snapshots],
        "plans": plan_rows,
        "gap": active["gap"] if active else _gap(live, None, False),
    }


async def projects_with_power_deficit(session: AsyncSession) -> set[uuid.UUID]:
    """Проекты, чей прогноз уже не помещается в текущий предел ввода."""
    overview = await power_service.overview(session)
    lacking: set[uuid.UUID] = set()
    for scenario in overview["scenarios"]:
        project_id = scenario.get("project_id")
        forecast = scenario.get("forecast") or {}
        if project_id and int(forecast.get("deficit_w") or 0) > 0:
            lacking.add(project_id)
    return lacking


def _gap(live: dict[str, Any], planned_limit: int | None, applied: bool) -> list[dict[str, str]]:
    if live["limit_w"] is None or live["target_w"] is None or live["required_w"] is None:
        return []
    findings = power_gap(
        current_limit_w=int(live["limit_w"]),
        target_estimated_w=int(live["target_w"]),
        required_input_w=int(live["required_w"]),
        planned_limit_w=planned_limit,
        applied=applied,
    )
    return [{"rule": item.rule, "level": item.level, "message": item.message} for item in findings]


def _planned_limit(items: list[ChangeItem]) -> int | None:
    for item in items:
        fields = (item.payload or {}).get("fields") or {}
        if item.operation == "UPDATE" and "max_load_w" in fields:
            return int(fields["max_load_w"])
    return None


def _plan_row(plan: PlannedChange, items: list[ChangeItem], live: dict[str, Any]) -> dict[str, Any]:
    applied = plan.status == "APPLIED"
    return {
        "id": plan.id,
        "name": plan.name,
        "status": plan.status,
        "applied_at": plan.applied_at,
        "base_snapshot_id": plan.base_snapshot_id,
        "result_snapshot_id": plan.result_snapshot_id,
        "gap": _gap(live, _planned_limit(items), applied),
        "items": [
            {
                "id": item.id,
                "operation": item.operation,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "payload": item.payload,
                "apply_status": item.apply_status,
                "order_index": item.order_index,
            }
            for item in items
        ],
    }


def _snapshot_row(snapshot: StateSnapshot) -> dict[str, Any]:
    payload = snapshot.payload or {}
    inlet = payload.get("input") or {}
    forecast = payload.get("forecast") or {}
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "checksum": snapshot.checksum,
        "taken_at": snapshot.taken_at,
        "estimated_w": inlet.get("estimated_w"),
        "limit_w": inlet.get("limit_w"),
        "headroom_w": inlet.get("headroom_w"),
        "target_w": forecast.get("target_estimated_w"),
        "deficit_w": forecast.get("deficit_w"),
    }


async def _plan(session: AsyncSession, project_id: uuid.UUID, plan_id: uuid.UUID) -> PlannedChange:
    plan = await session.get(PlannedChange, plan_id)
    if plan is None or plan.project_id != project_id:
        raise NotFound("План изменений не найден", entity_id=str(plan_id))
    return plan


async def _items(session: AsyncSession, plan_id: uuid.UUID) -> list[ChangeItem]:
    return list(
        (
            await session.execute(
                select(ChangeItem)
                .where(ChangeItem.planned_change_id == plan_id)
                .order_by(ChangeItem.order_index)
            )
        ).scalars()
    )


async def _append_architecture(
    session: AsyncSession,
    plan: PlannedChange,
    overview: dict[str, Any],
    primary: dict[str, Any],
) -> None:
    items = await _items(session, plan.id)
    if any((item.payload or {}).get("ref") == "R2" for item in items):
        return
    node = await session.get(PowerNode, primary["id"])
    if node is None:
        return
    ci = await session.get(Ci, node.id)
    location_id = str(ci.location_id) if ci is not None and ci.location_id else None
    panel = next(
        (row for row in overview["nodes"] if row["node_type"] == "PANEL" and row.get("code")),
        None,
    )
    other_inputs = [
        row
        for row in overview["nodes"]
        if row["node_type"] == "INPUT" and row["id"] != primary["id"] and row.get("code")
    ]
    side_b = next((row for row in other_inputs if row.get("feed_side") == "B"), None)
    if side_b is None and other_inputs:
        side_b = other_inputs[0]
    source = panel or primary
    specs = architecture_items(
        location_id=location_id,
        source_code=source["code"],
        source_is_panel=panel is not None,
        side_b_code=side_b["code"] if side_b else None,
    )
    start = max((item.order_index for item in items), default=-1) + 1
    for offset, spec in enumerate(specs):
        session.add(
            ChangeItem(
                planned_change_id=plan.id,
                operation=spec["operation"],
                entity_type=spec["entity_type"],
                order_index=start + offset,
                apply_status="PENDING",
                payload={
                    "ref": spec["ref"],
                    "summary": spec["summary"],
                    **({"create": spec["create"]} if "create" in spec else {}),
                    **({"connect": spec["connect"]} if "connect" in spec else {}),
                },
            )
        )
    if plan.name != TARGET_PLAN_NAME:
        plan.name = TARGET_PLAN_NAME
    await session.flush()


async def _apply_item(
    session: AsyncSession, item: ChangeItem, refs: dict[str, uuid.UUID]
) -> None:
    payload = item.payload or {}
    if item.operation == "UPDATE" and item.entity_type == "power_node":
        await _apply_update(session, item)
        return
    if item.operation == "CREATE" and item.entity_type == "rack":
        created = await rack_service.create_rack(session, _create_payload(payload, refs))
        entity_id = created["rack"]["id"]
        await _place_rack(session, entity_id, payload.get("create") or {})
    elif item.operation == "CREATE" and item.entity_type == "power_node":
        created = await power_service.create_node(session, _create_payload(payload, refs))
        entity_id = created["id"]
    elif item.operation == "CONNECT" and item.entity_type == "power_link":
        spec = payload.get("connect") or {}
        created = await power_service.create_link(
            session,
            {
                "source_node_id": await _endpoint(session, spec, "source", refs),
                "target_node_id": await _endpoint(session, spec, "target", refs),
            },
        )
        entity_id = created["id"]
    else:
        raise Invalid(
            "Операция плана не поддерживается",
            code_hint="unsupported_operation",
        )
    item.apply_status = "APPLIED"
    item.applied_entity_id = entity_id
    item.error = None
    ref = payload.get("ref")
    if ref:
        refs[ref] = entity_id


async def _apply_update(session: AsyncSession, item: ChangeItem) -> None:
    if item.entity_id is None:
        raise Invalid("У операции нет объекта", code_hint="missing_entity")
    node = await session.get(PowerNode, item.entity_id)
    if node is None:
        raise NotFound("Узел питания не найден", entity_id=str(item.entity_id))
    fields = (item.payload or {}).get("fields") or {}
    for key in _POWER_FIELDS:
        if key in fields:
            setattr(node, key, fields[key])
    item.apply_status = "APPLIED"
    item.applied_entity_id = node.id
    item.error = None


def _create_payload(payload: dict[str, Any], refs: dict[str, uuid.UUID]) -> dict[str, Any]:
    data = dict(payload.get("create") or {})
    if data.get("location_id"):
        data["location_id"] = uuid.UUID(str(data["location_id"]))
    rack_ref = data.pop("rack_ref", None)
    if rack_ref:
        data["rack_id"] = refs[rack_ref]
    return data


async def _endpoint(
    session: AsyncSession, spec: dict[str, Any], role: str, refs: dict[str, uuid.UUID]
) -> uuid.UUID:
    ref = spec.get(f"{role}_ref")
    if ref:
        return refs[ref]
    code = spec.get(f"{role}_code")
    ci = (
        await session.execute(select(Ci).where(Ci.code == code, Ci.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if ci is None:
        raise NotFound("Узел питания не найден", entity_id=str(code))
    return ci.id


async def _place_rack(session: AsyncSession, rack_id: uuid.UUID, data: dict[str, Any]) -> None:
    if data.get("plan_x") is None or not data.get("location_id"):
        return
    location_id = uuid.UUID(str(data["location_id"]))
    plan = (
        await session.execute(
            select(Floorplan).where(Floorplan.location_id == location_id).limit(1)
        )
    ).scalar_one_or_none()
    if plan is None:
        return
    await floorplan_service.place_item(
        session,
        plan.id,
        {"ci_id": rack_id, "x": data["plan_x"], "y": data["plan_y"]},
    )


async def _restore_item(session: AsyncSession, item: ChangeItem) -> None:
    if item.operation == "UPDATE" and item.entity_type == "power_node":
        if item.entity_id is None:
            raise Invalid("У операции нет объекта", code_hint="missing_entity")
        node = await session.get(PowerNode, item.entity_id)
        if node is None:
            raise NotFound("Узел питания не найден", entity_id=str(item.entity_id))
        before = (item.payload or {}).get("before") or {}
        for key in _POWER_FIELDS:
            if key in before:
                setattr(node, key, before[key])
        item.apply_status = "PENDING"
        item.applied_entity_id = None
        item.error = None
        return
    if item.operation == "CONNECT":
        if item.applied_entity_id is not None:
            link = await session.get(PowerLink, item.applied_entity_id)
            if link is not None:
                await session.delete(link)
                await session.flush()
        item.apply_status = "PENDING"
        item.applied_entity_id = None
        item.error = None
        return
    if item.operation == "CREATE":
        await _remove_created(session, item)
        return
    raise Invalid("Операция плана не поддерживается", code_hint="unsupported_operation")


async def _remove_created(session: AsyncSession, item: ChangeItem) -> None:
    entity_id = item.applied_entity_id
    item.apply_status = "PENDING"
    item.applied_entity_id = None
    item.error = None
    if entity_id is None:
        return
    placed = list(
        (
            await session.execute(
                select(FloorplanItem).where(FloorplanItem.ci_id == entity_id)
            )
        ).scalars()
    )
    for row in placed:
        await session.delete(row)
    node = await session.get(PowerNode, entity_id)
    if node is not None:
        await session.delete(node)
    rack = await session.get(Rack, entity_id)
    if rack is not None:
        await session.delete(rack)
    await session.flush()
    ci = await session.get(Ci, entity_id)
    if ci is not None:
        await search_service.remove_entity(session, "CI", ci.id)
        await session.delete(ci)
        await session.flush()
