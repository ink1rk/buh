from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.network import (
    DeviceRead,
    DeviceRow,
    DeviceWrite,
    InterfaceRow,
    InterfaceUpdate,
    InterfaceWrite,
    PortUsage,
    WarrantyRow,
)
from itms.domain.permissions import Permission
from itms.models.enums import DeviceRole
from itms.services import device_service, network_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=Page[DeviceRow], dependencies=[requires(Permission.CI_READ)])
async def list_devices(
    session: SessionDep,
    q: str | None = None,
    role: Annotated[list[DeviceRole] | None, Query()] = None,
    location_id: uuid.UUID | None = None,
    model_id: uuid.UUID | None = None,
    warranty_days: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[DeviceRow]:
    items, total = await device_service.list_devices(
        session,
        q=q,
        role=role,
        location_id=location_id,
        model_id=model_id,
        warranty_days=warranty_days,
        limit=limit,
        offset=offset,
    )
    return Page[DeviceRow](
        items=[DeviceRow.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/warranty", response_model=list[WarrantyRow],
            dependencies=[requires(Permission.CI_READ)])
async def expiring_warranties(session: SessionDep, days: int = 90) -> list[WarrantyRow]:
    rows = await device_service.expiring_warranties(session, days)
    return [WarrantyRow.model_validate(row) for row in rows]


@router.get("/{ci_id}", response_model=DeviceRead, dependencies=[requires(Permission.CI_READ)])
async def get_device(ci_id: uuid.UUID, session: SessionDep) -> DeviceRead:
    return DeviceRead.model_validate(await device_service.get_device(session, ci_id))


@router.put("/{ci_id}", response_model=DeviceRead,
            dependencies=[requires(Permission.CI_WRITE)])
async def upsert_device(
    ci_id: uuid.UUID, payload: DeviceWrite, session: SessionDep
) -> DeviceRead:
    device = await device_service.upsert_device(
        session, ci_id, payload.model_dump(exclude_unset=True)
    )
    return DeviceRead.model_validate(device)


@router.get("/{ci_id}/ports", response_model=PortUsage,
            dependencies=[requires(Permission.CI_READ)])
async def port_usage(ci_id: uuid.UUID, session: SessionDep) -> PortUsage:
    return PortUsage.model_validate(await device_service.port_usage(session, ci_id))


@router.get("/{ci_id}/interfaces", response_model=list[InterfaceRow],
            dependencies=[requires(Permission.CI_READ)])
async def list_interfaces(ci_id: uuid.UUID, session: SessionDep) -> list[InterfaceRow]:
    rows = await network_service.list_interfaces(session, ci_id)
    return [InterfaceRow.model_validate(row) for row in rows]


@router.post("/{ci_id}/interfaces", response_model=list[InterfaceRow], status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_interface(
    ci_id: uuid.UUID, payload: InterfaceWrite, session: SessionDep
) -> list[InterfaceRow]:
    await network_service.create_interface(session, ci_id, payload.model_dump(exclude_unset=True))
    rows = await network_service.list_interfaces(session, ci_id)
    return [InterfaceRow.model_validate(row) for row in rows]


@router.post("/{ci_id}/interfaces/from-model", response_model=list[InterfaceRow],
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_interfaces_from_model(
    ci_id: uuid.UUID, session: SessionDep
) -> list[InterfaceRow]:
    """Разворачивает шаблоны портов модели в интерфейсы устройства."""
    device = await device_service.get_device(session, ci_id)
    if device.device_model_id:
        await device_service.create_interfaces_from_model(
            session, ci_id, device.device_model_id
        )
    rows = await network_service.list_interfaces(session, ci_id)
    return [InterfaceRow.model_validate(row) for row in rows]


interfaces_router = APIRouter(prefix="/interfaces", tags=["network"])


@interfaces_router.patch("/{interface_id}", response_model=InterfaceRow,
                         dependencies=[requires(Permission.NETWORK_WRITE)])
async def update_interface(
    interface_id: uuid.UUID, payload: InterfaceUpdate, session: SessionDep
) -> InterfaceRow:
    interface = await network_service.update_interface(
        session, interface_id, payload.model_dump(exclude_unset=True)
    )
    rows = await network_service.list_interfaces(session, interface.ci_id)
    match = next(row for row in rows if row["id"] == interface_id)
    return InterfaceRow.model_validate(match)


@interfaces_router.delete("/{interface_id}", response_model=Ok,
                          dependencies=[requires(Permission.NETWORK_WRITE)])
async def delete_interface(interface_id: uuid.UUID, session: SessionDep) -> Ok:
    await network_service.delete_interface(session, interface_id)
    return Ok()
