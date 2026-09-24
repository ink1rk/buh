from __future__ import annotations

import uuid

from fastapi import APIRouter

from itms.api.deps import SessionDep, requires
from itms.api.schemas.virtualization import HostCreate, HostUpdate, VirtOverview, VmCreate, VmUpdate
from itms.domain.permissions import Permission
from itms.services import virtualization_service

router = APIRouter(prefix="/virtualization", tags=["virtualization"])


@router.get("", response_model=VirtOverview, dependencies=[requires(Permission.CI_READ)])
async def get_virtualization(session: SessionDep) -> VirtOverview:
    return VirtOverview.model_validate(await virtualization_service.overview(session))


@router.post(
    "/hosts",
    response_model=VirtOverview,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_host(payload: HostCreate, session: SessionDep) -> VirtOverview:
    overview = await virtualization_service.create_host(session, payload.model_dump())
    return VirtOverview.model_validate(overview)


@router.patch(
    "/hosts/{host_id}",
    response_model=VirtOverview,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_host(host_id: uuid.UUID, payload: HostUpdate, session: SessionDep) -> VirtOverview:
    overview = await virtualization_service.update_host(
        session, host_id, payload.model_dump(exclude_unset=True)
    )
    return VirtOverview.model_validate(overview)


@router.post(
    "/vms",
    response_model=VirtOverview,
    status_code=201,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def create_vm(payload: VmCreate, session: SessionDep) -> VirtOverview:
    overview = await virtualization_service.create_vm(session, payload.model_dump())
    return VirtOverview.model_validate(overview)


@router.patch(
    "/vms/{vm_id}",
    response_model=VirtOverview,
    dependencies=[requires(Permission.CI_WRITE)],
)
async def update_vm(vm_id: uuid.UUID, payload: VmUpdate, session: SessionDep) -> VirtOverview:
    overview = await virtualization_service.update_vm(
        session, vm_id, payload.model_dump(exclude_unset=True)
    )
    return VirtOverview.model_validate(overview)
