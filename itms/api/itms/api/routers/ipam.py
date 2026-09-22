from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from itms.api.deps import SessionDep, requires
from itms.api.schemas.common import Ok, Page
from itms.api.schemas.network import (
    IpAddressRead,
    IpAddressRow,
    IpAddressUpdate,
    IpAddressWrite,
    PrefixDetail,
    PrefixRow,
    PrefixUpdate,
    PrefixWrite,
    VlanRow,
    VlanUpdate,
    VlanWrite,
    VrfRead,
    VrfWrite,
)
from itms.domain.permissions import Permission
from itms.services import ipam_service

router = APIRouter(prefix="/ipam", tags=["ipam"])


@router.get("/vrfs", response_model=list[VrfRead], dependencies=[requires(Permission.CI_READ)])
async def list_vrfs(session: SessionDep) -> list[VrfRead]:
    return [VrfRead.model_validate(item) for item in await ipam_service.list_vrfs(session)]


@router.post("/vrfs", response_model=VrfRead, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_vrf(payload: VrfWrite, session: SessionDep) -> VrfRead:
    return VrfRead.model_validate(await ipam_service.create_vrf(session, payload.model_dump()))


@router.get("/vlans", response_model=list[VlanRow], dependencies=[requires(Permission.CI_READ)])
async def list_vlans(
    session: SessionDep, site_id: uuid.UUID | None = None, q: str | None = None
) -> list[VlanRow]:
    rows = await ipam_service.list_vlans(session, site_id=site_id, q=q)
    return [VlanRow.model_validate(row) for row in rows]


@router.post("/vlans", response_model=VlanRow, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_vlan(payload: VlanWrite, session: SessionDep) -> VlanRow:
    vlan = await ipam_service.create_vlan(session, payload.model_dump())
    rows = await ipam_service.list_vlans(session)
    return VlanRow.model_validate(next(row for row in rows if row["id"] == vlan.id))


@router.patch("/vlans/{vlan_id}", response_model=VlanRow,
              dependencies=[requires(Permission.NETWORK_WRITE)])
async def update_vlan(
    vlan_id: uuid.UUID, payload: VlanUpdate, session: SessionDep
) -> VlanRow:
    await ipam_service.update_vlan(session, vlan_id, payload.model_dump(exclude_unset=True))
    rows = await ipam_service.list_vlans(session)
    return VlanRow.model_validate(next(row for row in rows if row["id"] == vlan_id))


@router.get("/prefixes", response_model=list[PrefixRow],
            dependencies=[requires(Permission.CI_READ)])
async def list_prefixes(
    session: SessionDep, q: str | None = None, vrf_id: uuid.UUID | None = None
) -> list[PrefixRow]:
    rows = await ipam_service.list_prefixes(session, q=q, vrf_id=vrf_id)
    return [PrefixRow.model_validate(row) for row in rows]


@router.post("/prefixes", response_model=PrefixRow, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_prefix(payload: PrefixWrite, session: SessionDep) -> PrefixRow:
    prefix = await ipam_service.create_prefix(session, payload.model_dump())
    detail = await ipam_service.prefix_detail(session, prefix.id)
    return PrefixRow.model_validate(detail["prefix"])


@router.get("/prefixes/{prefix_id}", response_model=PrefixDetail,
            dependencies=[requires(Permission.CI_READ)])
async def prefix_detail(prefix_id: uuid.UUID, session: SessionDep) -> PrefixDetail:
    return PrefixDetail.model_validate(await ipam_service.prefix_detail(session, prefix_id))


@router.patch("/prefixes/{prefix_id}", response_model=PrefixRow,
              dependencies=[requires(Permission.NETWORK_WRITE)])
async def update_prefix(
    prefix_id: uuid.UUID, payload: PrefixUpdate, session: SessionDep
) -> PrefixRow:
    await ipam_service.update_prefix(session, prefix_id, payload.model_dump(exclude_unset=True))
    detail = await ipam_service.prefix_detail(session, prefix_id)
    return PrefixRow.model_validate(detail["prefix"])


@router.get("/addresses", response_model=Page[IpAddressRow],
            dependencies=[requires(Permission.CI_READ)])
async def list_addresses(
    session: SessionDep,
    q: str | None = None,
    prefix_id: uuid.UUID | None = None,
    ci_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[IpAddressRow]:
    items, total = await ipam_service.list_addresses(
        session, q=q, prefix_id=prefix_id, ci_id=ci_id, limit=limit, offset=offset
    )
    return Page[IpAddressRow](
        items=[IpAddressRow.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/addresses", response_model=IpAddressRead, status_code=201,
             dependencies=[requires(Permission.NETWORK_WRITE)])
async def create_address(payload: IpAddressWrite, session: SessionDep) -> IpAddressRead:
    address = await ipam_service.create_address(session, payload.model_dump(exclude_unset=True))
    return IpAddressRead.model_validate(address)


@router.patch("/addresses/{address_id}", response_model=IpAddressRead,
              dependencies=[requires(Permission.NETWORK_WRITE)])
async def update_address(
    address_id: uuid.UUID, payload: IpAddressUpdate, session: SessionDep
) -> IpAddressRead:
    address = await ipam_service.update_address(
        session, address_id, payload.model_dump(exclude_unset=True)
    )
    return IpAddressRead.model_validate(address)


@router.delete("/addresses/{address_id}", response_model=Ok,
               dependencies=[requires(Permission.NETWORK_WRITE)])
async def delete_address(address_id: uuid.UUID, session: SessionDep) -> Ok:
    await ipam_service.delete_address(session, address_id)
    return Ok()
