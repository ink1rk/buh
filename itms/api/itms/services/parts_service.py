"""Комплектация устройства: процессоры, плата, память, диски и адаптеры.

Лимиты берутся из модели шасси. Если установлена материнская плата со своими
сокетами и слотами, для процессоров и памяти действуют её цифры.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from itms.core.errors import Invalid, NotFound
from itms.domain.platform_slots import cpu_names, ram_names
from itms.models.catalog import DeviceModel
from itms.models.enums import INSTALLABLE_COMPONENTS, ComponentClass
from itms.models.network import Device, DevicePart
from itms.services import catalog_service, device_service


@dataclass(frozen=True, slots=True)
class PlatformLimits:
    cpu_sockets: int | None
    cpu_socket: str | None
    ram_slots: int | None
    ram_type: str | None
    drive_bays: int | None
    drive_form: str | None
    psu_count: int | None


def _as_class(value: str | ComponentClass) -> ComponentClass:
    try:
        return ComponentClass(value)
    except ValueError as exc:
        raise Invalid("Неизвестный тип комплектующего", field="component_class") from exc


def limits_for(host: DeviceModel | None, parts: list[DevicePart]) -> PlatformLimits:
    board = next(
        (
            part.component
            for part in parts
            if part.component.component_class == ComponentClass.BOARD
        ),
        None,
    )
    source = board or host
    return PlatformLimits(
        cpu_sockets=source.cpu_sockets if source else None,
        cpu_socket=source.cpu_socket if source else None,
        ram_slots=source.ram_slots if source else None,
        ram_type=source.ram_type if source else None,
        drive_bays=host.drive_bays if host else None,
        drive_form=host.drive_form if host else None,
        psu_count=host.psu_count if host and host.psu_count else None,
    )


def _check(parts: list[DevicePart], host: DeviceModel | None) -> None:
    limits = limits_for(host, parts)
    totals: dict[ComponentClass, int] = {}
    boards = 0
    for part in parts:
        kind = _as_class(part.component.component_class)
        totals[kind] = totals.get(kind, 0) + part.quantity
        if kind == ComponentClass.BOARD:
            boards += part.quantity
            if part.quantity != 1:
                raise Invalid("Материнская плата ставится в одном экземпляре")
        cpu_socket = part.component.cpu_socket
        if (
            kind == ComponentClass.CPU
            and limits.cpu_socket
            and cpu_socket
            and cpu_socket != limits.cpu_socket
        ):
            raise Invalid(
                f"Процессор {part.component.model} рассчитан на {cpu_socket}, "
                f"платформа — на {limits.cpu_socket}"
            )
        ram_type = part.component.ram_type
        ram_mismatch = (
            kind == ComponentClass.MEMORY
            and limits.ram_type
            and ram_type
            and ram_type != limits.ram_type
        )
        if ram_mismatch:
            raise Invalid(
                f"Модуль {part.component.model} — {ram_type}, платформа принимает {limits.ram_type}"
            )
    if boards > 1:
        raise Invalid("В устройство ставится одна материнская плата")
    if limits.cpu_sockets is not None and totals.get(ComponentClass.CPU, 0) > limits.cpu_sockets:
        raise Invalid(f"Процессоров больше, чем сокетов ({limits.cpu_sockets})")
    if limits.ram_slots is not None and totals.get(ComponentClass.MEMORY, 0) > limits.ram_slots:
        raise Invalid(f"Модулей памяти больше, чем слотов ({limits.ram_slots})")
    if limits.drive_bays is not None and totals.get(ComponentClass.DISK, 0) > limits.drive_bays:
        raise Invalid(f"Дисков больше, чем корзин ({limits.drive_bays})")
    if limits.psu_count is not None and totals.get(ComponentClass.PSU, 0) > limits.psu_count:
        raise Invalid(f"Блоков питания больше, чем посадочных мест ({limits.psu_count})")


async def list_parts(session: AsyncSession, ci_id: uuid.UUID) -> tuple[Device, list[DevicePart]]:
    device = await device_service.get_device(session, ci_id)
    stmt = (
        select(DevicePart)
        .options(
            selectinload(DevicePart.component).selectinload(DeviceModel.port_templates),
            selectinload(DevicePart.component).selectinload(DeviceModel.manufacturer),
        )
        .where(DevicePart.device_id == device.id)
        .order_by(DevicePart.created_at)
    )
    parts = list((await session.execute(stmt)).scalars().unique())
    return device, parts


def _place(
    kind: ComponentClass,
    quantity: int,
    slots: list[str] | None,
    limits: PlatformLimits,
    others: list[DevicePart],
) -> list[str] | None:
    names = cpu_names(limits.cpu_sockets) if kind == ComponentClass.CPU else []
    if kind == ComponentClass.MEMORY:
        names = ram_names(limits.ram_slots, limits.cpu_sockets)
    if kind not in {ComponentClass.CPU, ComponentClass.MEMORY} or not names:
        return None
    used = {name for part in others for name in (part.slots or [])}
    chosen = slots
    if chosen is None:
        free = [name for name in names if name not in used]
        if len(free) < quantity:
            label = "сокетов" if kind == ComponentClass.CPU else "слотов памяти"
            raise Invalid(f"Свободных {label} меньше, чем ставите: {len(free)}")
        return free[:quantity]
    if len(chosen) != quantity:
        raise Invalid("Число мест на плате не совпадает с количеством")
    if len(set(chosen)) != len(chosen):
        raise Invalid("Одно место на плате указано дважды")
    unknown = [name for name in chosen if name not in names]
    if unknown:
        raise Invalid(f"На платформе нет места {unknown[0]}")
    taken = [name for name in chosen if name in used]
    if taken:
        raise Invalid(f"Место {taken[0]} уже занято")
    return chosen


async def set_part(
    session: AsyncSession,
    ci_id: uuid.UUID,
    component_model_id: uuid.UUID,
    quantity: int,
    slots: list[str] | None = None,
) -> DevicePart:
    if quantity < 1:
        raise Invalid("Количество должно быть не меньше 1")
    device = await device_service.get_device(session, ci_id)
    if device.model is None:
        raise Invalid(
            "Сначала выберите модель устройства: по ней известны сокеты, слоты и корзины"
        )
    component = await catalog_service.get_model(session, component_model_id)
    kind = _as_class(component.component_class)
    if kind not in INSTALLABLE_COMPONENTS:
        raise Invalid(
            "В комплектацию ставятся плата, процессор, память, диск, адаптер или блок питания"
        )
    _, current = await list_parts(session, ci_id)
    existing = next((part for part in current if part.component_model_id == component.id), None)
    draft = [part for part in current if part is not existing]
    if existing is None:
        existing = DevicePart(
            device_id=device.id, component_model_id=component.id, quantity=quantity
        )
        existing.component = component
        session.add(existing)
    else:
        existing.quantity = quantity
    limits = limits_for(device.model, draft)
    existing.slots = _place(kind, quantity, slots, limits, draft)
    draft.append(existing)
    _check(draft, device.model)
    await session.flush()
    return existing


async def delete_part(session: AsyncSession, ci_id: uuid.UUID, part_id: uuid.UUID) -> None:
    device = await device_service.get_device(session, ci_id)
    part = await session.get(DevicePart, part_id)
    if part is None or part.device_id != device.id:
        raise NotFound("Комплектующее не найдено", entity_id=str(part_id))
    await session.delete(part)
    await session.flush()
