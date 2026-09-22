from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.racks import (
    MountWrite,
    RackCreate,
    RackElevation,
    RackSummary,
    RackUpdate,
)
from itms.domain.permissions import Permission
from itms.services import rack_service

router = APIRouter(prefix="/racks", tags=["racks"])


@router.get("", response_model=list[RackSummary], dependencies=[requires(Permission.CI_READ)])
async def list_racks(session: SessionDep) -> list[RackSummary]:
    rows = await rack_service.list_racks(session)
    return [RackSummary.model_validate(row) for row in rows]


@router.post("", response_model=RackElevation, status_code=201,
             dependencies=[requires(Permission.CI_WRITE)])
async def create_rack(payload: RackCreate, session: SessionDep) -> RackElevation:
    elevation = await rack_service.create_rack(session, payload.model_dump())
    return RackElevation.model_validate(elevation)


@router.get("/{rack_id}", response_model=RackElevation,
            dependencies=[requires(Permission.CI_READ)])
async def get_rack(rack_id: uuid.UUID, session: SessionDep) -> RackElevation:
    return RackElevation.model_validate(await rack_service.elevation(session, rack_id))


@router.patch("/{rack_id}", response_model=RackElevation,
              dependencies=[requires(Permission.CI_WRITE)])
async def update_rack(
    rack_id: uuid.UUID, payload: RackUpdate, session: SessionDep
) -> RackElevation:
    elevation = await rack_service.update_rack(
        session, rack_id, payload.model_dump(exclude_unset=True)
    )
    return RackElevation.model_validate(elevation)


@router.put("/{rack_id}/mounts", response_model=RackElevation,
            dependencies=[requires(Permission.CI_WRITE)])
async def place_mount(
    rack_id: uuid.UUID, payload: MountWrite, session: SessionDep
) -> RackElevation:
    """Ставит оборудование в стойку или переносит уже стоящее."""
    elevation = await rack_service.place_mount(
        session, rack_id, payload.model_dump(exclude_unset=True)
    )
    return RackElevation.model_validate(elevation)


@router.delete("/{rack_id}/mounts/{mount_id}", response_model=RackElevation,
               dependencies=[requires(Permission.CI_WRITE)])
async def remove_mount(
    rack_id: uuid.UUID, mount_id: uuid.UUID, session: SessionDep, to_stock: bool = False
) -> RackElevation:
    """Снимает оборудование со стойки. На склад переводит только работающий объект."""
    elevation = await rack_service.remove_mount(session, rack_id, mount_id, to_stock=to_stock)
    return RackElevation.model_validate(elevation)
