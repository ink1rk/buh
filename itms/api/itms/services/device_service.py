"""Устройства: инженерный профиль объекта CMDB и его порты."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Invalid, NotFound
from itms.domain.network import expand_port_template, normalize_mac
from itms.models.catalog import DeviceModel, Manufacturer, PortTemplate
from itms.models.cmdb import Ci, Location
from itms.models.enums import PATCHABLE_INTERFACE_TYPES, CiType, DeviceRole
from itms.models.network import Connection, Device, Interface, IpAddress
from itms.services import ci_service

DEVICE_FIELDS = (
    "device_model_id",
    "device_role",
    "asset_tag",
    "hostname",
    "mgmt_ip",
    "mgmt_mac",
    "firmware",
    "os_version",
    "purchase_date",
    "warranty_until",
    "psu_count",
    "power_nameplate_w",
    "power_max_w",
    "notes",
)


async def get_device(session: AsyncSession, ci_id: uuid.UUID) -> Device:
    device = await session.get(Device, ci_id)
    if device is None:
        raise NotFound("У объекта нет инженерного профиля устройства", entity_id=str(ci_id))
    return device


async def find_device(session: AsyncSession, ci_id: uuid.UUID) -> Device | None:
    return await session.get(Device, ci_id)


async def _ensure_device_ci(session: AsyncSession, ci_id: uuid.UUID) -> Ci:
    ci = await ci_service.get_ci(session, ci_id)
    if ci.ci_type != CiType.DEVICE:
        raise Invalid(
            "Профиль устройства заводится только для объектов типа DEVICE", code_hint="not_a_device"
        )
    return ci


async def _ensure_unique_asset_tag(
    session: AsyncSession, asset_tag: str | None, exclude: uuid.UUID | None
) -> None:
    if not asset_tag:
        return
    stmt = select(Device.id).where(func.lower(Device.asset_tag) == asset_tag.lower())
    if exclude:
        stmt = stmt.where(Device.id != exclude)
    if (await session.execute(stmt.limit(1))).scalar_one_or_none():
        raise Conflict(
            f"Инвентарная метка «{asset_tag}» уже занята", field="asset_tag"
        )


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in data.items() if k in DEVICE_FIELDS}
    if "mgmt_mac" in payload:
        payload["mgmt_mac"] = normalize_mac(payload["mgmt_mac"])
    return payload


async def upsert_device(session: AsyncSession, ci_id: uuid.UUID, data: dict[str, Any]) -> Device:
    """Создаёт или обновляет профиль устройства для существующего объекта CMDB."""
    await _ensure_device_ci(session, ci_id)
    payload = _clean(data)
    await _ensure_unique_asset_tag(session, payload.get("asset_tag"), exclude=ci_id)
    if payload.get("device_model_id"):
        model = await session.get(DeviceModel, payload["device_model_id"])
        if model is None:
            raise NotFound("Модель не найдена", entity_id=str(payload["device_model_id"]))

    device = await session.get(Device, ci_id)
    created = device is None
    if device is None:
        device = Device(id=ci_id, device_role=payload.get("device_role", DeviceRole.OTHER))
        session.add(device)
    for field, value in payload.items():
        setattr(device, field, value)
    await session.flush()
    if created and device.device_model_id:
        await create_interfaces_from_model(session, ci_id, device.device_model_id)
    await session.refresh(device)
    await session.refresh(device, attribute_names=["model"])
    await reindex_device(session, ci_id)
    return device


async def create_interfaces_from_model(
    session: AsyncSession, ci_id: uuid.UUID, model_id: uuid.UUID
) -> list[Interface]:
    """Разворачивает шаблоны портов модели в реальные интерфейсы устройства.

    Уже существующие имена пропускаются: повторный вызов не ломает ручные правки.
    """
    templates = list(
        (
            await session.execute(
                select(PortTemplate)
                .where(PortTemplate.device_model_id == model_id)
                .order_by(PortTemplate.position, PortTemplate.name_pattern)
            )
        ).scalars()
    )
    if not templates:
        return []
    taken = {
        name
        for (name,) in await session.execute(
            select(Interface.name).where(Interface.ci_id == ci_id)
        )
    }
    # Позиция сквозная по всем шаблонам: иначе медные и оптические порты
    # получат одинаковые номера и перемешаются в списке.
    position = int(
        (
            await session.execute(
                select(func.coalesce(func.max(Interface.position), 0)).where(
                    Interface.ci_id == ci_id
                )
            )
        ).scalar_one()
    )
    created: list[Interface] = []
    for template in templates:
        for name, _index in expand_port_template(
            template.name_pattern, template.count, template.start_index
        ):
            if name in taken:
                continue
            position += 1
            interface = Interface(
                ci_id=ci_id,
                name=name,
                position=position,
                interface_type=template.interface_type,
                speed_mbps=template.speed_mbps,
                poe_mode="CAPABLE" if template.poe_capable else None,
            )
            session.add(interface)
            created.append(interface)
            taken.add(name)
    await session.flush()
    return created


async def reindex_device(session: AsyncSession, ci_id: uuid.UUID) -> None:
    """Пересобирает поисковые ключи объекта с учётом hostname, IP, MAC и имён портов."""
    ci = await ci_service.get_ci(session, ci_id)
    device = await session.get(Device, ci_id)
    location_path = None
    if ci.location_id:
        location_path = (
            await session.execute(select(Location.path).where(Location.id == ci.location_id))
        ).scalar_one_or_none()
    extra: list[str | None] = []
    if device is not None:
        extra += [device.hostname, device.asset_tag, str(device.mgmt_ip or ""), device.mgmt_mac]
    interface_rows = await session.execute(
        select(Interface.name, Interface.mac).where(Interface.ci_id == ci_id)
    )
    for name, mac in interface_rows:
        extra += [name, mac]
    ip_rows = await session.execute(
        select(IpAddress.address, IpAddress.dns_name).where(
            or_(
                IpAddress.ci_id == ci_id,
                IpAddress.interface_id.in_(
                    select(Interface.id).where(Interface.ci_id == ci_id)
                ),
            )
        )
    )
    for address, dns_name in ip_rows:
        extra += [str(address), dns_name]
    await ci_service.reindex_with_keywords(session, ci, location_path, extra)


async def list_devices(
    session: AsyncSession,
    q: str | None = None,
    role: list[DeviceRole] | None = None,
    location_id: uuid.UUID | None = None,
    model_id: uuid.UUID | None = None,
    warranty_days: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        select(Device, Ci, DeviceModel, Manufacturer)
        .join(Ci, Ci.id == Device.id)
        .outerjoin(DeviceModel, DeviceModel.id == Device.device_model_id)
        .outerjoin(Manufacturer, Manufacturer.id == DeviceModel.manufacturer_id)
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
    )
    if role:
        stmt = stmt.where(Device.device_role.in_(role))
    if location_id:
        stmt = stmt.where(Ci.location_id == location_id)
    if model_id:
        stmt = stmt.where(Device.device_model_id == model_id)
    if warranty_days is not None:
        edge = date.today() + timedelta(days=warranty_days)
        stmt = stmt.where(Device.warranty_until.isnot(None), Device.warranty_until <= edge)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Ci.name).like(pattern),
                func.lower(Ci.code).like(pattern),
                func.lower(Device.hostname).like(pattern),
                func.lower(Ci.serial_number).like(pattern),
                func.lower(Device.asset_tag).like(pattern),
            )
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = await session.execute(stmt.order_by(Ci.name).limit(limit).offset(offset))
    items = [
        {
            "id": device.id,
            "name": ci.name,
            "code": ci.code,
            "status": ci.status,
            "criticality": ci.criticality,
            "location_id": ci.location_id,
            "device_role": device.device_role,
            "hostname": device.hostname,
            "mgmt_ip": str(device.mgmt_ip) if device.mgmt_ip else None,
            "serial_number": ci.serial_number,
            "asset_tag": device.asset_tag,
            "warranty_until": device.warranty_until,
            "model_label": (
                f"{manufacturer.name} {model.model}" if model and manufacturer else None
            ),
        }
        for device, ci, model, manufacturer in rows
    ]
    return items, int(total)


async def port_usage(session: AsyncSession, ci_id: uuid.UUID) -> dict[str, int]:
    """Сколько физических портов у устройства и сколько из них свободно."""
    occupied = select(Connection.a_interface_id).where(
        Connection.status.in_(("ACTIVE", "RESERVED"))
    ).union(
        select(Connection.b_interface_id).where(Connection.status.in_(("ACTIVE", "RESERVED")))
    )
    taken = {row[0] for row in await session.execute(occupied)}
    rows = await session.execute(
        select(Interface.id, Interface.interface_type).where(Interface.ci_id == ci_id)
    )
    total = 0
    free = 0
    for interface_id, interface_type in rows:
        if interface_type not in PATCHABLE_INTERFACE_TYPES:
            continue
        total += 1
        if interface_id not in taken:
            free += 1
    return {"total": total, "free": free, "used": total - free}


async def expiring_warranties(session: AsyncSession, days: int = 90) -> list[dict[str, Any]]:
    edge = datetime.now(UTC).date() + timedelta(days=days)
    rows = await session.execute(
        select(Ci.id, Ci.name, Device.warranty_until, Device.device_role)
        .join(Device, Device.id == Ci.id)
        .where(
            Ci.deleted_at.is_(None),
            Device.warranty_until.isnot(None),
            Device.warranty_until <= edge,
        )
        .order_by(Device.warranty_until)
    )
    return [
        {"id": ci_id, "name": name, "warranty_until": until, "device_role": role}
        for ci_id, name, until, role in rows
    ]
