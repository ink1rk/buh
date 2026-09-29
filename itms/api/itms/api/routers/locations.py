from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.cmdb import LocationCreate, LocationNode, LocationRead, LocationUpdate
from itms.domain.permissions import Permission
from itms.services import location_service

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead], dependencies=[requires(Permission.CI_READ)])
async def list_locations(session: SessionDep, archived: bool = False) -> list[LocationRead]:
    items = await location_service.list_locations(session, archived=archived)
    return [LocationRead.model_validate(item) for item in items]


@router.get("/tree", response_model=list[LocationNode],
            dependencies=[requires(Permission.CI_READ)])
async def location_tree(session: SessionDep) -> list[LocationNode]:
    return [LocationNode.model_validate(node) for node in await location_service.tree(session)]


@router.post("", response_model=LocationRead, status_code=201,
             dependencies=[requires(Permission.LOCATION_WRITE)])
async def create_location(payload: LocationCreate, session: SessionDep) -> LocationRead:
    data = payload.model_dump(exclude_unset=True)
    location = await location_service.create_location(session, data)
    return LocationRead.model_validate(location)


@router.get("/{location_id}", response_model=LocationRead,
            dependencies=[requires(Permission.CI_READ)])
async def get_location(location_id: uuid.UUID, session: SessionDep) -> LocationRead:
    return LocationRead.model_validate(await location_service.get_location(session, location_id))


@router.patch("/{location_id}", response_model=LocationRead,
              dependencies=[requires(Permission.LOCATION_WRITE)])
async def update_location(
    location_id: uuid.UUID, payload: LocationUpdate, session: SessionDep
) -> LocationRead:
    location = await location_service.update_location(
        session, location_id, payload.model_dump(exclude_unset=True)
    )
    return LocationRead.model_validate(location)


@router.post("/{location_id}/archive", response_model=LocationRead,
             dependencies=[requires(Permission.LOCATION_WRITE)])
async def archive_location(location_id: uuid.UUID, session: SessionDep) -> LocationRead:
    return LocationRead.model_validate(
        await location_service.archive_location(session, location_id)
    )
