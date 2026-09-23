"""Каталог оборудования: производители, модели, шаблоны портов."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from itms.core.errors import Conflict, NotFound
from itms.domain.catalog_library import LIBRARY
from itms.domain.network import expand_port_template
from itms.models.catalog import DeviceModel, Manufacturer, PortTemplate
from itms.models.network import Device

MANUFACTURER_FIELDS = ("name", "support_url", "notes")
MODEL_FIELDS = (
    "manufacturer_id",
    "model",
    "part_number",
    "default_role",
    "u_height",
    "is_full_depth",
    "depth_mm",
    "weight_kg",
    "psu_count",
    "power_nameplate_w",
    "power_max_w",
    "power_factor",
    "utilization_factor",
    "airflow",
    "notes",
)
TEMPLATE_FIELDS = (
    "name_pattern",
    "count",
    "start_index",
    "interface_type",
    "speed_mbps",
    "poe_capable",
    "position",
)


# --- Производители ------------------------------------------------------------


async def list_manufacturers(session: AsyncSession, q: str | None = None) -> list[Manufacturer]:
    stmt = select(Manufacturer).order_by(Manufacturer.name)
    if q:
        stmt = stmt.where(func.lower(Manufacturer.name).like(f"%{q.lower()}%"))
    return list((await session.execute(stmt)).scalars())


async def get_manufacturer(session: AsyncSession, manufacturer_id: uuid.UUID) -> Manufacturer:
    item = await session.get(Manufacturer, manufacturer_id)
    if item is None:
        raise NotFound("Производитель не найден", entity_id=str(manufacturer_id))
    return item


async def create_manufacturer(session: AsyncSession, data: dict[str, Any]) -> Manufacturer:
    exists = (
        await session.execute(
            select(Manufacturer.id).where(func.lower(Manufacturer.name) == data["name"].lower())
        )
    ).scalar_one_or_none()
    if exists:
        raise Conflict(f"Производитель «{data['name']}» уже есть в каталоге", field="name")
    item = Manufacturer(**{k: v for k, v in data.items() if k in MANUFACTURER_FIELDS})
    session.add(item)
    await session.flush()
    return item


async def update_manufacturer(
    session: AsyncSession, manufacturer_id: uuid.UUID, data: dict[str, Any]
) -> Manufacturer:
    item = await get_manufacturer(session, manufacturer_id)
    for field in MANUFACTURER_FIELDS:
        if field in data:
            setattr(item, field, data[field])
    await session.flush()
    return item


# --- Модели -------------------------------------------------------------------


async def list_models(
    session: AsyncSession,
    q: str | None = None,
    manufacturer_id: uuid.UUID | None = None,
    role: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[DeviceModel], int]:
    stmt = select(DeviceModel).join(Manufacturer, Manufacturer.id == DeviceModel.manufacturer_id)
    if manufacturer_id:
        stmt = stmt.where(DeviceModel.manufacturer_id == manufacturer_id)
    if role:
        stmt = stmt.where(DeviceModel.default_role == role)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(DeviceModel.model).like(pattern),
                func.lower(DeviceModel.part_number).like(pattern),
                func.lower(Manufacturer.name).like(pattern),
            )
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = (
        stmt.options(selectinload(DeviceModel.port_templates))
        .order_by(Manufacturer.name, DeviceModel.model)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().unique()), int(total)


async def get_model(session: AsyncSession, model_id: uuid.UUID) -> DeviceModel:
    stmt = (
        select(DeviceModel)
        .options(selectinload(DeviceModel.port_templates))
        .where(DeviceModel.id == model_id)
    )
    item = (await session.execute(stmt)).scalars().unique().one_or_none()
    if item is None:
        raise NotFound("Модель не найдена", entity_id=str(model_id))
    return item


async def _ensure_unique_model(
    session: AsyncSession,
    manufacturer_id: uuid.UUID,
    model: str,
    exclude: uuid.UUID | None = None,
) -> None:
    stmt = select(DeviceModel.id).where(
        DeviceModel.manufacturer_id == manufacturer_id, DeviceModel.model == model
    )
    if exclude:
        stmt = stmt.where(DeviceModel.id != exclude)
    if (await session.execute(stmt.limit(1))).scalar_one_or_none():
        raise Conflict(f"Модель «{model}» у этого производителя уже заведена", field="model")


async def create_model(session: AsyncSession, data: dict[str, Any]) -> DeviceModel:
    await get_manufacturer(session, data["manufacturer_id"])
    await _ensure_unique_model(session, data["manufacturer_id"], data["model"])
    templates = data.pop("port_templates", None) or []
    item = DeviceModel(**{k: v for k, v in data.items() if k in MODEL_FIELDS})
    session.add(item)
    await session.flush()
    for template in templates:
        await add_port_template(session, item.id, template)
    return await get_model(session, item.id)


async def update_model(
    session: AsyncSession, model_id: uuid.UUID, data: dict[str, Any]
) -> DeviceModel:
    item = await get_model(session, model_id)
    if "model" in data or "manufacturer_id" in data:
        await _ensure_unique_model(
            session,
            data.get("manufacturer_id", item.manufacturer_id),
            data.get("model", item.model),
            exclude=model_id,
        )
    for field in MODEL_FIELDS:
        if field in data:
            setattr(item, field, data[field])
    await session.flush()
    return await get_model(session, model_id)


async def delete_model(session: AsyncSession, model_id: uuid.UUID) -> None:
    """Модель удаляется, только пока по ней нет ни одного устройства."""
    item = await get_model(session, model_id)
    used = (
        await session.execute(
            select(func.count()).select_from(Device).where(Device.device_model_id == model_id)
        )
    ).scalar_one()
    if used:
        raise Conflict(
            f"По модели заведено устройств: {used}. Сначала переназначьте их на другую модель",
            count=int(used),
        )
    await session.delete(item)
    await session.flush()


# --- Шаблоны портов -----------------------------------------------------------


async def add_port_template(
    session: AsyncSession, model_id: uuid.UUID, data: dict[str, Any]
) -> PortTemplate:
    await get_model(session, model_id)
    # Разворачиваем шаблон сразу: ошибка в маске должна всплыть при сохранении модели,
    # а не при заведении первого устройства.
    expand_port_template(
        data["name_pattern"], int(data.get("count", 1)), int(data.get("start_index", 1))
    )
    template = PortTemplate(
        device_model_id=model_id, **{k: v for k, v in data.items() if k in TEMPLATE_FIELDS}
    )
    session.add(template)
    await session.flush()
    return template


async def install_library(session: AsyncSession) -> dict[str, int]:
    """Ставит библиотеку моделей. Повторный вызов не создаёт дубликаты."""
    manufacturers: dict[str, Manufacturer] = {}
    created_manufacturers = 0
    skipped_manufacturers = 0
    created_models = 0
    skipped_models = 0
    for spec in LIBRARY:
        key = spec.manufacturer.lower()
        if key not in manufacturers:
            found = (
                await session.execute(
                    select(Manufacturer).where(func.lower(Manufacturer.name) == key)
                )
            ).scalar_one_or_none()
            if found is None:
                found = await create_manufacturer(
                    session, {"name": spec.manufacturer, "notes": "Библиотека каталога"}
                )
                created_manufacturers += 1
            else:
                skipped_manufacturers += 1
            manufacturers[key] = found
        manufacturer = manufacturers[key]
        exists = (
            await session.execute(
                select(DeviceModel.id)
                .where(
                    DeviceModel.manufacturer_id == manufacturer.id,
                    DeviceModel.model == spec.model,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if exists:
            skipped_models += 1
            continue
        await create_model(
            session,
            {
                "manufacturer_id": manufacturer.id,
                "model": spec.model,
                "default_role": spec.default_role,
                "u_height": spec.u_height,
                "is_full_depth": spec.is_full_depth,
                "weight_kg": spec.weight_kg,
                "psu_count": spec.psu_count,
                "power_nameplate_w": spec.power_nameplate_w,
                "power_max_w": spec.power_max_w,
                "notes": spec.notes,
                "port_templates": [
                    {
                        "name_pattern": port.name_pattern,
                        "count": port.count,
                        "start_index": port.start_index,
                        "interface_type": port.interface_type,
                        "speed_mbps": port.speed_mbps,
                        "poe_capable": port.poe_capable,
                        "position": port.position,
                    }
                    for port in spec.ports
                ],
            },
        )
        created_models += 1
    return {
        "manufacturers_created": created_manufacturers,
        "manufacturers_skipped": skipped_manufacturers,
        "models_created": created_models,
        "models_skipped": skipped_models,
    }


async def delete_port_template(session: AsyncSession, template_id: uuid.UUID) -> None:
    template = await session.get(PortTemplate, template_id)
    if template is None:
        raise NotFound("Шаблон портов не найден", entity_id=str(template_id))
    await session.delete(template)
    await session.flush()


def template_preview(template: PortTemplate) -> list[str]:
    names = [
        name
        for name, _ in expand_port_template(
            template.name_pattern, template.count, template.start_index
        )
    ]
    return names if len(names) <= 6 else [*names[:3], "…", *names[-2:]]
