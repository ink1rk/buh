from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.network import (
    DeviceModelRead,
    DeviceModelUpdate,
    DeviceModelWrite,
    LibraryInstallRead,
    ManufacturerRead,
    ManufacturerWrite,
    PortTemplateRead,
    PortTemplateWrite,
)
from itms.domain.permissions import Permission
from itms.services import catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post(
    "/library", response_model=LibraryInstallRead, dependencies=[requires(Permission.CATALOG_WRITE)]
)
async def install_library(session: SessionDep) -> LibraryInstallRead:
    return LibraryInstallRead.model_validate(await catalog_service.install_library(session))


@router.get(
    "/manufacturers",
    response_model=list[ManufacturerRead],
    dependencies=[requires(Permission.CI_READ)],
)
async def list_manufacturers(session: SessionDep, q: str | None = None) -> list[ManufacturerRead]:
    items = await catalog_service.list_manufacturers(session, q)
    return [ManufacturerRead.model_validate(item) for item in items]


@router.post(
    "/manufacturers",
    response_model=ManufacturerRead,
    status_code=201,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def create_manufacturer(payload: ManufacturerWrite, session: SessionDep) -> ManufacturerRead:
    item = await catalog_service.create_manufacturer(session, payload.model_dump())
    return ManufacturerRead.model_validate(item)


@router.patch(
    "/manufacturers/{manufacturer_id}",
    response_model=ManufacturerRead,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def update_manufacturer(
    manufacturer_id: uuid.UUID, payload: ManufacturerWrite, session: SessionDep
) -> ManufacturerRead:
    item = await catalog_service.update_manufacturer(
        session, manufacturer_id, payload.model_dump(exclude_unset=True)
    )
    return ManufacturerRead.model_validate(item)


@router.get(
    "/models", response_model=Page[DeviceModelRead], dependencies=[requires(Permission.CI_READ)]
)
async def list_models(
    session: SessionDep,
    q: str | None = None,
    manufacturer_id: uuid.UUID | None = None,
    role: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> Page[DeviceModelRead]:
    items, total = await catalog_service.list_models(
        session, q=q, manufacturer_id=manufacturer_id, role=role, limit=limit, offset=offset
    )
    return Page[DeviceModelRead](
        items=[DeviceModelRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/models",
    response_model=DeviceModelRead,
    status_code=201,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def create_model(payload: DeviceModelWrite, session: SessionDep) -> DeviceModelRead:
    item = await catalog_service.create_model(session, payload.model_dump())
    return DeviceModelRead.model_validate(item)


@router.get(
    "/models/{model_id}",
    response_model=DeviceModelRead,
    dependencies=[requires(Permission.CI_READ)],
)
async def get_model(model_id: uuid.UUID, session: SessionDep) -> DeviceModelRead:
    return DeviceModelRead.model_validate(await catalog_service.get_model(session, model_id))


@router.patch(
    "/models/{model_id}",
    response_model=DeviceModelRead,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def update_model(
    model_id: uuid.UUID, payload: DeviceModelUpdate, session: SessionDep
) -> DeviceModelRead:
    item = await catalog_service.update_model(
        session, model_id, payload.model_dump(exclude_unset=True)
    )
    return DeviceModelRead.model_validate(item)


@router.delete(
    "/models/{model_id}", response_model=Ok, dependencies=[requires(Permission.CATALOG_WRITE)]
)
async def delete_model(model_id: uuid.UUID, session: SessionDep) -> Ok:
    await catalog_service.delete_model(session, model_id)
    return Ok()


@router.post(
    "/models/{model_id}/port-templates",
    response_model=PortTemplateRead,
    status_code=201,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def add_port_template(
    model_id: uuid.UUID, payload: PortTemplateWrite, session: SessionDep
) -> PortTemplateRead:
    template = await catalog_service.add_port_template(session, model_id, payload.model_dump())
    return PortTemplateRead.model_validate(template)


@router.delete(
    "/port-templates/{template_id}",
    response_model=Ok,
    dependencies=[requires(Permission.CATALOG_WRITE)],
)
async def delete_port_template(template_id: uuid.UUID, session: SessionDep) -> Ok:
    await catalog_service.delete_port_template(session, template_id)
    return Ok()
