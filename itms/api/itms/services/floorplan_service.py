"""План помещения: стойки и щиты стоят в миллиметрах и не пересекаются."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.floorplan import (
    PANEL_DEPTH_MM,
    PANEL_WIDTH_MM,
    RACK_WIDTH_MM,
    Box,
    inside,
    overlaps,
)
from itms.models.cmdb import Ci, Location
from itms.models.datacenter import Rack
from itms.models.enums import CiType, PowerNodeType
from itms.models.floorplan import Floorplan, FloorplanItem
from itms.models.power import PowerNode


async def list_plans(session: AsyncSession) -> list[dict[str, Any]]:
    plans = list((await session.execute(select(Floorplan).order_by(Floorplan.name))).scalars())
    if not plans:
        return []
    locations = {
        row.id: row
        for row in (
            await session.execute(
                select(Location).where(Location.id.in_([plan.location_id for plan in plans]))
            )
        ).scalars()
    }
    counts: dict[uuid.UUID, int] = {}
    for plan_id in (await session.execute(select(FloorplanItem.floorplan_id))).scalars():
        counts[plan_id] = counts.get(plan_id, 0) + 1
    return [
        {
            "id": plan.id,
            "name": plan.name,
            "location_id": plan.location_id,
            "location_name": (
                locations[plan.location_id].name if plan.location_id in locations else None
            ),
            "width_mm": plan.width_mm,
            "height_mm": plan.height_mm,
            "item_count": counts.get(plan.id, 0),
        }
        for plan in plans
    ]


async def create_plan(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    location = await session.get(Location, data["location_id"])
    if location is None:
        raise NotFound("Размещение не найдено", entity_id=str(data["location_id"]))
    plan = Floorplan(
        location_id=location.id,
        name=data["name"].strip(),
        width_mm=data["width_mm"],
        height_mm=data["height_mm"],
    )
    session.add(plan)
    await session.flush()
    return await view(session, plan.id)


async def view(session: AsyncSession, plan_id: uuid.UUID) -> dict[str, Any]:
    plan = await _plan(session, plan_id)
    location = await session.get(Location, plan.location_id)
    items = await _items(session, plan.id)
    cis = await _cis(session, [item.ci_id for item in items if item.ci_id])
    available = await _available(session, plan, {item.ci_id for item in items if item.ci_id})
    return {
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "location_id": plan.location_id,
            "location_name": location.name if location else None,
            "width_mm": plan.width_mm,
            "height_mm": plan.height_mm,
        },
        "items": [_item_row(item, cis.get(item.ci_id) if item.ci_id else None) for item in items],
        "available": available,
    }


async def place_item(
    session: AsyncSession, plan_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    plan = await _plan(session, plan_id)
    ci, kind, width, height = await _subject(session, data["ci_id"])
    existing = (
        await session.execute(
            select(FloorplanItem.id).where(
                FloorplanItem.floorplan_id == plan.id,
                FloorplanItem.ci_id == ci.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("Объект уже стоит на этом плане", code_hint="floorplan_duplicate")
    rotation = int(data.get("rotation") or 0)
    box = Box(float(data["x"]), float(data["y"]), width, height, rotation)
    await _assert_fits(session, plan, box, ignore=None)
    session.add(
        FloorplanItem(
            floorplan_id=plan.id,
            ci_id=ci.id,
            item_kind=kind,
            x=box.x,
            y=box.y,
            width=width,
            height=height,
            rotation=rotation,
            label=ci.name,
            style={},
        )
    )
    await session.flush()
    await _sync_rack(session, ci.id, kind, box)
    return await view(session, plan.id)


async def move_item(
    session: AsyncSession, plan_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    plan = await _plan(session, plan_id)
    item = await session.get(FloorplanItem, item_id)
    if item is None or item.floorplan_id != plan.id:
        raise NotFound("Объект на плане не найден", entity_id=str(item_id))
    if "rotation" in data and data["rotation"] is not None:
        rotation = int(data["rotation"])
    else:
        rotation = item.rotation
    box = Box(
        float(data.get("x", item.x)),
        float(data.get("y", item.y)),
        float(item.width),
        float(item.height),
        rotation,
    )
    await _assert_fits(session, plan, box, ignore=item.id)
    item.x = box.x
    item.y = box.y
    item.rotation = rotation
    await session.flush()
    if item.ci_id is not None:
        await _sync_rack(session, item.ci_id, item.item_kind, box)
    return await view(session, plan.id)


async def remove_item(
    session: AsyncSession, plan_id: uuid.UUID, item_id: uuid.UUID
) -> dict[str, Any]:
    plan = await _plan(session, plan_id)
    item = await session.get(FloorplanItem, item_id)
    if item is None or item.floorplan_id != plan.id:
        raise NotFound("Объект на плане не найден", entity_id=str(item_id))
    if item.ci_id is not None and item.item_kind == "RACK":
        rack = await session.get(Rack, item.ci_id)
        if rack is not None:
            rack.plan_x = None
            rack.plan_y = None
    await session.delete(item)
    await session.flush()
    return await view(session, plan.id)


async def _assert_fits(
    session: AsyncSession, plan: Floorplan, box: Box, ignore: uuid.UUID | None
) -> None:
    if box.rotation not in (0, 90, 180, 270):
        raise Invalid("Поворот задаётся как 0, 90, 180 или 270 градусов", code_hint="invalid")
    if not inside(box, plan.width_mm, plan.height_mm):
        raise Invalid("Объект выходит за границу помещения", code_hint="floorplan_outside")
    for item in await _items(session, plan.id):
        if item.id == ignore:
            continue
        other = Box(
            float(item.x),
            float(item.y),
            float(item.width),
            float(item.height),
            item.rotation,
        )
        if overlaps(box, other):
            raise Invalid("Объекты на плане пересекаются", code_hint="floorplan_overlap")


async def _subject(session: AsyncSession, ci_id: uuid.UUID) -> tuple[Ci, str, float, float]:
    ci = await session.get(Ci, ci_id)
    if ci is None or ci.deleted_at is not None:
        raise NotFound("Объект не найден", entity_id=str(ci_id))
    if ci.ci_type == CiType.RACK:
        rack = await session.get(Rack, ci.id)
        depth = float(rack.depth_mm) if rack is not None else 1000
        return ci, "RACK", float(RACK_WIDTH_MM), depth
    if ci.ci_type == CiType.POWER_NODE:
        node = await session.get(PowerNode, ci.id)
        if node is not None and node.node_type == PowerNodeType.PANEL:
            return ci, "POWER", float(PANEL_WIDTH_MM), float(PANEL_DEPTH_MM)
    raise Invalid(
        "На план помещения ставятся стойки и щиты",
        code_hint="floorplan_kind",
    )


async def _sync_rack(session: AsyncSession, ci_id: uuid.UUID, kind: str, box: Box) -> None:
    if kind != "RACK":
        return
    rack = await session.get(Rack, ci_id)
    if rack is None:
        return
    rack.plan_x = box.x
    rack.plan_y = box.y
    rack.plan_rotation = box.rotation


async def _available(
    session: AsyncSession, plan: Floorplan, placed: set[uuid.UUID]
) -> list[dict[str, Any]]:
    location_ids = await _location_ids(session, plan.location_id)
    cis = list(
        (
            await session.execute(
                select(Ci).where(
                    Ci.location_id.in_(location_ids),
                    Ci.deleted_at.is_(None),
                    Ci.ci_type.in_((CiType.RACK, CiType.POWER_NODE)),
                )
            )
        ).scalars()
    )
    rows = []
    for ci in cis:
        if ci.id in placed:
            continue
        try:
            _, kind, width, height = await _subject(session, ci.id)
        except Invalid:
            continue
        rows.append(
            {
                "ci_id": ci.id,
                "code": ci.code,
                "name": ci.name,
                "item_kind": kind,
                "width": width,
                "height": height,
            }
        )
    rows.sort(key=lambda row: (row["item_kind"], row["name"]))
    return rows


async def _location_ids(session: AsyncSession, location_id: uuid.UUID) -> list[uuid.UUID]:
    root = await session.get(Location, location_id)
    if root is None:
        return []
    rows = await session.execute(
        select(Location.id).where(
            or_(Location.id == root.id, Location.path.like(f"{root.path} / %"))
        )
    )
    return list(rows.scalars())


async def _plan(session: AsyncSession, plan_id: uuid.UUID) -> Floorplan:
    plan = await session.get(Floorplan, plan_id)
    if plan is None:
        raise NotFound("План помещения не найден", entity_id=str(plan_id))
    return plan


async def _items(session: AsyncSession, plan_id: uuid.UUID) -> list[FloorplanItem]:
    return list(
        (
            await session.execute(
                select(FloorplanItem)
                .where(FloorplanItem.floorplan_id == plan_id)
                .order_by(FloorplanItem.y, FloorplanItem.x)
            )
        ).scalars()
    )


async def _cis(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Ci]:
    if not ids:
        return {}
    return {ci.id: ci for ci in (await session.execute(select(Ci).where(Ci.id.in_(ids)))).scalars()}


def _item_row(item: FloorplanItem, ci: Ci | None) -> dict[str, Any]:
    return {
        "id": item.id,
        "ci_id": item.ci_id,
        "code": ci.code if ci else None,
        "name": (ci.name if ci else None) or item.label or "—",
        "item_kind": item.item_kind,
        "x": float(item.x),
        "y": float(item.y),
        "width": float(item.width),
        "height": float(item.height),
        "rotation": item.rotation,
    }
