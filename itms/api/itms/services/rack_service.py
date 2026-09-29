"""Стойки: профиль объекта RACK и размещение оборудования по юнитам."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.lifecycle import validate_status_transition
from itms.domain.racks import (
    COMMISSION_STATUSES,
    ensure_within_rack,
    free_blocks,
    occupies,
    placement_warnings,
    spans_overlap,
    units_for_model,
)
from itms.models.catalog import DeviceModel
from itms.models.cmdb import Ci, Location
from itms.models.datacenter import Rack, RackMount
from itms.models.enums import CiStatus, CiType, RackFace, RackFormFactor
from itms.models.network import Device
from itms.services import ci_service

RACK_FIELDS = (
    "u_height",
    "width_in",
    "depth_mm",
    "max_weight_kg",
    "max_power_w",
    "form_factor",
    "descending_units",
    "plan_x",
    "plan_y",
    "plan_rotation",
)

WARNING_TEXT = {
    "weight_exceeded": "Суммарный вес превышает предел стойки",
    "power_exceeded": "Суммарная мощность превышает предел стойки",
    "depth_exceeded": "Глубина устройства больше глубины стойки",
}


async def list_racks(session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(Rack, Ci, Location)
        .join(Ci, Ci.id == Rack.id)
        .outerjoin(Location, Location.id == Ci.location_id)
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .order_by(Ci.name)
    )
    racks = list(rows.all())
    if not racks:
        return []
    mounts = await _mounts_for(session, [rack.id for rack, _, _ in racks])
    by_rack: dict[uuid.UUID, list[RackMount]] = {}
    for mount in mounts:
        by_rack.setdefault(mount.rack_id, []).append(mount)
    powers = await _power_by_ci(session, [mount.ci_id for mount in mounts])
    return [
        _summary(rack, ci, location, by_rack.get(rack.id, []), powers)
        for rack, ci, location in racks
    ]


async def get_rack(session: AsyncSession, rack_id: uuid.UUID) -> Rack:
    rack = await session.get(Rack, rack_id)
    if rack is None:
        raise NotFound("Стойка не найдена", entity_id=str(rack_id))
    return rack


async def create_rack(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    ci = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.RACK,
            "name": data["name"].strip(),
            "code": data.get("code"),
            "location_id": data.get("location_id"),
            "description": data.get("description"),
            "status": CiStatus.ACTIVE,
        },
    )
    rack = Rack(id=ci.id, **_rack_payload(data))
    session.add(rack)
    await session.flush()
    return await elevation(session, rack.id)


async def update_rack(
    session: AsyncSession, rack_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    rack = await get_rack(session, rack_id)
    ci_keys = ("name", "code", "description", "location_id")
    ci_fields = {key: data[key] for key in ci_keys if key in data}
    if ci_fields:
        await ci_service.update_ci(session, rack_id, ci_fields)
    payload = _rack_payload(data)
    if "u_height" in payload:
        mounts = await _mounts_for(session, [rack_id])
        highest = max(
            (mount.position_u + mount.u_height - 1 for mount in mounts if mount.u_height > 0),
            default=0,
        )
        if payload["u_height"] < highest:
            raise Conflict(
                f"В стойке заняты юниты до U{highest}",
                code_hint="rack_too_short",
            )
    for field, value in payload.items():
        setattr(rack, field, value)
    await session.flush()
    return await elevation(session, rack_id)


async def elevation(session: AsyncSession, rack_id: uuid.UUID) -> dict[str, Any]:
    rack = await get_rack(session, rack_id)
    ci = await ci_service.get_ci(session, rack_id)
    location = await session.get(Location, ci.location_id) if ci.location_id else None
    mounts = await _mount_rows(session, rack_id)
    payload = [_mount_payload(mount, item, device, model) for mount, item, device, model in mounts]
    powers = {row["ci_id"]: row["power_w"] or 0 for row in payload}
    weights = {row["ci_id"]: row["weight_kg"] or 0 for row in payload}
    return {
        "rack": _rack_payload_read(rack, ci, location),
        "mounts": payload,
        "free_front": _free(rack, payload, "FRONT"),
        "free_rear": _free(rack, payload, "REAR"),
        "capacity": _capacity(rack, payload, powers, weights),
        "warehouse": await _warehouse(session),
    }


async def place_mount(
    session: AsyncSession, rack_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    rack = await get_rack(session, rack_id)
    ci = await ci_service.get_ci(session, data["ci_id"])
    if ci.ci_type != CiType.DEVICE:
        raise Invalid("В стойку ставится оборудование", code_hint="not_rack_equipment")
    device = await session.get(Device, ci.id)
    model = None
    if device and device.device_model_id:
        model = await session.get(DeviceModel, device.device_model_id)
    u_height = data.get("u_height")
    if u_height is None:
        u_height = units_for_model(float(model.u_height) if model else 1)
    position_u = int(data.get("position_u") or 1)
    face = RackFace(data.get("face") or RackFace.FRONT)
    zero_u_side = data.get("zero_u_side")
    if u_height == 0 and not zero_u_side:
        raise Invalid("Для оборудования без юнитов укажите борт стойки", code_hint="zero_u_side")
    if u_height > 0:
        zero_u_side = None
    ensure_within_rack(position_u, u_height, rack.u_height)

    existing = (
        await session.execute(select(RackMount).where(RackMount.ci_id == ci.id))
    ).scalar_one_or_none()
    others = [
        mount
        for mount in await _mounts_for(session, [rack_id])
        if existing is None or mount.id != existing.id
    ]
    reservation = bool(data.get("is_reservation"))
    if u_height > 0 and not reservation:
        _ensure_no_overlap(others, position_u, u_height, face.value)

    depth_mm = data.get("depth_mm")
    if depth_mm is None and model is not None:
        depth_mm = model.depth_mm
    weight_kg = data.get("weight_kg")
    if weight_kg is None and model is not None and model.weight_kg is not None:
        weight_kg = float(model.weight_kg)
    power_w = _device_power(device, model)
    total_weight, total_power = await _totals_after(
        session, others, weight_kg, power_w, reservation
    )
    warnings = placement_warnings(
        weight_kg=total_weight,
        max_weight_kg=float(rack.max_weight_kg) if rack.max_weight_kg is not None else None,
        power_w=total_power,
        max_power_w=rack.max_power_w,
        depth_mm=depth_mm,
        rack_depth_mm=rack.depth_mm,
    )
    if warnings and not data.get("confirm_warnings"):
        raise Conflict(
            ". ".join(WARNING_TEXT[code] for code in warnings),
            code_hint=warnings[0] if len(warnings) == 1 else "placement_warning",
            warnings=warnings,
        )

    if existing is None:
        existing = RackMount(rack_id=rack_id, ci_id=ci.id, position_u=position_u, u_height=u_height)
        session.add(existing)
    existing.rack_id = rack_id
    existing.position_u = position_u
    existing.u_height = u_height
    existing.face = face
    existing.zero_u_side = zero_u_side
    existing.depth_mm = depth_mm
    existing.weight_kg = weight_kg
    existing.is_reservation = reservation
    if not reservation and ci.status.value in COMMISSION_STATUSES:
        validate_status_transition(ci.status, CiStatus.ACTIVE)
        ci.status = CiStatus.ACTIVE
    await session.flush()
    return await elevation(session, rack_id)


async def remove_mount(
    session: AsyncSession, rack_id: uuid.UUID, mount_id: uuid.UUID, *, to_stock: bool
) -> dict[str, Any]:
    mount = await session.get(RackMount, mount_id)
    if mount is None or mount.rack_id != rack_id:
        raise NotFound("Размещение не найдено", entity_id=str(mount_id))
    ci = await ci_service.get_ci(session, mount.ci_id)
    await session.delete(mount)
    if to_stock and ci.status == CiStatus.ACTIVE:
        validate_status_transition(ci.status, CiStatus.IN_STOCK)
        ci.status = CiStatus.IN_STOCK
    await session.flush()
    return await elevation(session, rack_id)


def _rack_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = {key: data[key] for key in RACK_FIELDS if key in data and data[key] is not None}
    if "form_factor" in payload and payload["form_factor"] is not None:
        payload["form_factor"] = RackFormFactor(payload["form_factor"])
    return payload


def _summary(
    rack: Rack,
    ci: Ci,
    location: Location | None,
    mounts: list[RackMount],
    powers: dict[uuid.UUID, int],
) -> dict[str, Any]:
    active = [mount for mount in mounts if not mount.is_reservation and mount.u_height > 0]
    front = [(m.position_u, m.u_height) for m in active if occupies(m.face.value, "FRONT")]
    rear = [(m.position_u, m.u_height) for m in active if occupies(m.face.value, "REAR")]
    free_front = free_blocks(rack.u_height, front)
    weight = sum(float(mount.weight_kg or 0) for mount in mounts if not mount.is_reservation)
    power = sum(powers.get(mount.ci_id, 0) for mount in mounts if not mount.is_reservation)
    return {
        "id": rack.id,
        "name": ci.name,
        "code": ci.code,
        "location_id": ci.location_id,
        "location_path": location.path if location else None,
        "u_height": rack.u_height,
        "form_factor": rack.form_factor,
        "used_front": sum(height for _, height in front),
        "used_rear": sum(height for _, height in rear),
        "largest_free_front": max((block["length"] for block in free_front), default=0),
        "weight_kg": weight,
        "max_weight_kg": float(rack.max_weight_kg) if rack.max_weight_kg is not None else None,
        "power_w": power,
        "max_power_w": rack.max_power_w,
    }


def _rack_payload_read(rack: Rack, ci: Ci, location: Location | None) -> dict[str, Any]:
    return {
        "id": rack.id,
        "name": ci.name,
        "code": ci.code,
        "location_id": ci.location_id,
        "location_path": location.path if location else None,
        "description": ci.description,
        "u_height": rack.u_height,
        "width_in": rack.width_in,
        "depth_mm": rack.depth_mm,
        "max_weight_kg": float(rack.max_weight_kg) if rack.max_weight_kg is not None else None,
        "max_power_w": rack.max_power_w,
        "form_factor": rack.form_factor,
        "descending_units": rack.descending_units,
    }


def _mount_payload(
    mount: RackMount, ci: Ci, device: Device | None, model: DeviceModel | None
) -> dict[str, Any]:
    return {
        "id": mount.id,
        "ci_id": ci.id,
        "name": ci.name,
        "code": ci.code,
        "status": ci.status,
        "device_role": device.device_role if device else None,
        "position_u": mount.position_u,
        "u_height": mount.u_height,
        "face": mount.face,
        "zero_u_side": mount.zero_u_side,
        "depth_mm": mount.depth_mm,
        "weight_kg": float(mount.weight_kg) if mount.weight_kg is not None else None,
        "power_w": _device_power(device, model),
        "is_reservation": mount.is_reservation,
    }


def _free(rack: Rack, mounts: list[dict[str, Any]], face: str) -> list[dict[str, int]]:
    spans = [
        (mount["position_u"], mount["u_height"])
        for mount in mounts
        if not mount["is_reservation"] and occupies(_face(mount), face)
    ]
    return free_blocks(rack.u_height, spans)


def _capacity(
    rack: Rack,
    mounts: list[dict[str, Any]],
    powers: dict[uuid.UUID, int],
    weights: dict[uuid.UUID, float],
) -> dict[str, Any]:
    active = [mount for mount in mounts if not mount["is_reservation"]]
    return {
        "u_height": rack.u_height,
        "used_front": sum(
            m["u_height"] for m in active if m["u_height"] and occupies(_face(m), "FRONT")
        ),
        "used_rear": sum(
            m["u_height"] for m in active if m["u_height"] and occupies(_face(m), "REAR")
        ),
        "weight_kg": sum(weights.get(m["ci_id"], 0) for m in active),
        "max_weight_kg": float(rack.max_weight_kg) if rack.max_weight_kg is not None else None,
        "power_w": sum(powers.get(m["ci_id"], 0) for m in active),
        "max_power_w": rack.max_power_w,
    }


def _face(mount: dict[str, Any]) -> str:
    face = mount["face"]
    return face.value if hasattr(face, "value") else str(face)


def _ensure_no_overlap(
    others: list[RackMount], position_u: int, u_height: int, face: str
) -> None:
    for other in others:
        if other.is_reservation or other.u_height <= 0:
            continue
        if not occupies(face, other.face.value):
            continue
        if spans_overlap(position_u, u_height, other.position_u, other.u_height):
            raise Conflict(
                f"Юниты U{position_u}–U{position_u + u_height - 1} уже заняты",
                code_hint="u_overlap",
            )


async def _totals_after(
    session: AsyncSession,
    others: list[RackMount],
    weight_kg: float | None,
    power_w: int | None,
    reservation: bool,
) -> tuple[float | None, int | None]:
    if reservation:
        return weight_kg, power_w
    active = [other for other in others if not other.is_reservation]
    powers = await _power_by_ci(session, [other.ci_id for other in active])
    weight = float(weight_kg or 0) + sum(float(other.weight_kg or 0) for other in active)
    power = int(power_w or 0) + sum(powers.values())
    return weight, power


def _device_power(device: Device | None, model: DeviceModel | None) -> int | None:
    if device and device.power_nameplate_w is not None:
        return device.power_nameplate_w
    if model and model.power_nameplate_w is not None:
        return model.power_nameplate_w
    return None


async def _mounts_for(session: AsyncSession, rack_ids: list[uuid.UUID]) -> list[RackMount]:
    if not rack_ids:
        return []
    rows = await session.execute(select(RackMount).where(RackMount.rack_id.in_(rack_ids)))
    return list(rows.scalars())


async def _mount_rows(session: AsyncSession, rack_id: uuid.UUID):
    rows = await session.execute(
        select(RackMount, Ci, Device, DeviceModel)
        .join(Ci, Ci.id == RackMount.ci_id)
        .outerjoin(Device, Device.id == Ci.id)
        .outerjoin(DeviceModel, DeviceModel.id == Device.device_model_id)
        .where(RackMount.rack_id == rack_id)
        .order_by(RackMount.position_u)
    )
    return list(rows.all())


async def _power_by_ci(session: AsyncSession, ci_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ci_ids:
        return {}
    rows = await session.execute(
        select(Device.id, Device.power_nameplate_w, DeviceModel.power_nameplate_w)
        .outerjoin(DeviceModel, DeviceModel.id == Device.device_model_id)
        .where(Device.id.in_(ci_ids))
    )
    result: dict[uuid.UUID, int] = {}
    for ci_id, own, model_power in rows:
        value = own if own is not None else model_power
        if value is not None:
            result[ci_id] = int(value)
    return result


async def _warehouse(session: AsyncSession) -> list[dict[str, Any]]:
    """Всё оборудование, которое ещё не стоит ни в одной стойке."""
    mounted = select(RackMount.ci_id)
    rows = await session.execute(
        select(Ci, Device, DeviceModel)
        .outerjoin(Device, Device.id == Ci.id)
        .outerjoin(DeviceModel, DeviceModel.id == Device.device_model_id)
        .where(
            Ci.ci_type == CiType.DEVICE,
            Ci.deleted_at.is_(None),
            Ci.archived_at.is_(None),
            Ci.id.not_in(mounted),
        )
        .order_by(Ci.name)
        .limit(200)
    )
    items = []
    for ci, device, model in rows:
        items.append(
            {
                "ci_id": ci.id,
                "name": ci.name,
                "code": ci.code,
                "status": ci.status,
                "device_role": device.device_role if device else None,
                "u_height": units_for_model(float(model.u_height) if model else 1),
                "power_w": _device_power(device, model),
                "weight_kg": (
                    float(model.weight_kg) if model and model.weight_kg is not None else None
                ),
            }
        )
    return items
