"""Адресация: VRF, VLAN, подсети, IP-адреса и их занятость."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from itms.core.errors import Conflict, NotFound
from itms.domain.ipam import (
    ensure_address_in_prefix,
    next_free_addresses,
    parse_address,
    parse_network,
    prefix_capacity,
)
from itms.models.cmdb import Ci, Location
from itms.models.enums import IpStatus
from itms.models.network import Interface, IpAddress, Prefix, Vlan, Vrf

VRF_FIELDS = ("name", "rd", "description")
VLAN_FIELDS = ("vid", "name", "site_id", "purpose", "description")
PREFIX_FIELDS = ("cidr", "vrf_id", "vlan_id", "gateway", "dhcp_from", "dhcp_to", "site_id",
                 "description")
IP_FIELDS = ("address", "vrf_id", "prefix_id", "interface_id", "ci_id", "dns_name", "role",
             "status", "description")


# --- VRF ----------------------------------------------------------------------


async def list_vrfs(session: AsyncSession) -> list[Vrf]:
    return list((await session.execute(select(Vrf).order_by(Vrf.name))).scalars())


async def create_vrf(session: AsyncSession, data: dict[str, Any]) -> Vrf:
    duplicate = (
        await session.execute(select(Vrf.id).where(Vrf.name == data["name"]))
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict(f"VRF «{data['name']}» уже существует", field="name")
    vrf = Vrf(**{k: v for k, v in data.items() if k in VRF_FIELDS})
    session.add(vrf)
    await session.flush()
    return vrf


# --- VLAN ---------------------------------------------------------------------


async def list_vlans(
    session: AsyncSession, site_id: uuid.UUID | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(Vlan, Location.name).outerjoin(Location, Location.id == Vlan.site_id)
    if site_id:
        stmt = stmt.where(Vlan.site_id == site_id)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Vlan.name).like(pattern), cast(Vlan.vid, String).like(f"%{q}%"))
        )
    rows = await session.execute(stmt.order_by(Vlan.vid))
    counts = {
        vlan_id: int(total)
        for vlan_id, total in await session.execute(
            select(Prefix.vlan_id, func.count()).group_by(Prefix.vlan_id)
        )
    }
    return [
        {
            "id": vlan.id,
            "vid": vlan.vid,
            "name": vlan.name,
            "site_id": vlan.site_id,
            "site_name": site_name,
            "purpose": vlan.purpose,
            "description": vlan.description,
            "prefix_count": counts.get(vlan.id, 0),
        }
        for vlan, site_name in rows
    ]


async def create_vlan(session: AsyncSession, data: dict[str, Any]) -> Vlan:
    duplicate = (
        await session.execute(
            select(Vlan.id).where(Vlan.vid == data["vid"], Vlan.site_id == data.get("site_id"))
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict(f"VLAN {data['vid']} на этой площадке уже заведён", field="vid")
    vlan = Vlan(**{k: v for k, v in data.items() if k in VLAN_FIELDS})
    session.add(vlan)
    await session.flush()
    return vlan


async def update_vlan(session: AsyncSession, vlan_id: uuid.UUID, data: dict[str, Any]) -> Vlan:
    vlan = await session.get(Vlan, vlan_id)
    if vlan is None:
        raise NotFound("VLAN не найден", entity_id=str(vlan_id))
    for field in VLAN_FIELDS:
        if field in data:
            setattr(vlan, field, data[field])
    await session.flush()
    return vlan


# --- Подсети ------------------------------------------------------------------


async def get_prefix(session: AsyncSession, prefix_id: uuid.UUID) -> Prefix:
    prefix = (
        await session.execute(
            select(Prefix)
            .options(selectinload(Prefix.vlan), selectinload(Prefix.vrf))
            .where(Prefix.id == prefix_id)
        )
    ).scalars().unique().one_or_none()
    if prefix is None:
        raise NotFound("Подсеть не найдена", entity_id=str(prefix_id))
    return prefix


async def list_prefixes(
    session: AsyncSession, q: str | None = None, vrf_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    stmt = select(Prefix).options(selectinload(Prefix.vlan), selectinload(Prefix.vrf))
    if vrf_id:
        stmt = stmt.where(Prefix.vrf_id == vrf_id)
    if q:
        stmt = stmt.where(
            or_(
                cast(Prefix.cidr, String).like(f"%{q}%"),
                func.lower(Prefix.description).like(f"%{q.lower()}%"),
            )
        )
    prefixes = list((await session.execute(stmt.order_by(Prefix.cidr))).scalars().unique())
    used = {
        prefix_id: int(total)
        for prefix_id, total in await session.execute(
            select(IpAddress.prefix_id, func.count())
            .where(IpAddress.status != IpStatus.DEPRECATED)
            .group_by(IpAddress.prefix_id)
        )
    }
    return [_prefix_row(prefix, used.get(prefix.id, 0)) for prefix in prefixes]


def _prefix_row(prefix: Prefix, used: int) -> dict[str, Any]:
    network = parse_network(str(prefix.cidr))
    capacity = prefix_capacity(str(prefix.cidr), [])
    free = max(capacity.usable_total - used, 0)
    return {
        "id": prefix.id,
        "cidr": str(prefix.cidr),
        "version": network.version,
        "vrf_id": prefix.vrf_id,
        "vrf_name": prefix.vrf.name if prefix.vrf else None,
        "vlan_id": prefix.vlan_id,
        "vlan_label": f"{prefix.vlan.vid} · {prefix.vlan.name}" if prefix.vlan else None,
        "gateway": str(prefix.gateway) if prefix.gateway else None,
        "site_id": prefix.site_id,
        "description": prefix.description,
        "usable_total": capacity.usable_total,
        "used": used,
        "free": free,
        "utilisation_pct": (
            round(used / capacity.usable_total * 100, 1) if capacity.usable_total else 0.0
        ),
    }


async def create_prefix(session: AsyncSession, data: dict[str, Any]) -> Prefix:
    network = parse_network(str(data["cidr"]))
    payload = {k: v for k, v in data.items() if k in PREFIX_FIELDS}
    payload["cidr"] = str(network)
    duplicate = (
        await session.execute(
            select(Prefix.id).where(
                Prefix.cidr == payload["cidr"], Prefix.vrf_id == payload.get("vrf_id")
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict(f"Подсеть {network} в этом VRF уже заведена", field="cidr")
    if payload.get("gateway"):
        ensure_address_in_prefix(str(payload["gateway"]), str(network))
    prefix = Prefix(**payload)
    session.add(prefix)
    await session.flush()
    await attach_orphan_addresses(session, prefix)
    return await get_prefix(session, prefix.id)


async def update_prefix(
    session: AsyncSession, prefix_id: uuid.UUID, data: dict[str, Any]
) -> Prefix:
    prefix = await get_prefix(session, prefix_id)
    if data.get("gateway"):
        ensure_address_in_prefix(str(data["gateway"]), str(prefix.cidr))
    for field in PREFIX_FIELDS:
        if field in data and field != "cidr":
            setattr(prefix, field, data[field])
    await session.flush()
    return await get_prefix(session, prefix_id)


async def attach_orphan_addresses(session: AsyncSession, prefix: Prefix) -> int:
    """Привязывает к новой подсети адреса, которые физически в неё попадают."""
    rows = await session.execute(
        select(IpAddress).where(
            IpAddress.prefix_id.is_(None),
            IpAddress.vrf_id.is_not_distinct_from(prefix.vrf_id),
        )
    )
    network = parse_network(str(prefix.cidr))
    attached = 0
    for address in rows.scalars():
        if parse_address(str(address.address)).ip in network:
            address.prefix_id = prefix.id
            attached += 1
    if attached:
        await session.flush()
    return attached


async def prefix_detail(session: AsyncSession, prefix_id: uuid.UUID) -> dict[str, Any]:
    prefix = await get_prefix(session, prefix_id)
    addresses, _ = await list_addresses(session, prefix_id=prefix_id, limit=1000)
    capacity = prefix_capacity(
        str(prefix.cidr),
        [item["address"] for item in addresses if item["status"] != IpStatus.DEPRECATED],
    )
    free = next_free_addresses(
        str(prefix.cidr),
        [item["address"] for item in addresses],
        limit=5,
        skip=[str(prefix.gateway)] if prefix.gateway else [],
    )
    return {
        "prefix": _prefix_row(prefix, capacity.used),
        "capacity": {
            "usable_total": capacity.usable_total,
            "used": capacity.used,
            "free": capacity.free,
            "utilisation_pct": capacity.utilisation_pct,
            "network_address": capacity.network_address,
            "broadcast_address": capacity.broadcast_address,
            "netmask": capacity.netmask,
        },
        "next_free": free,
        "addresses": addresses,
    }


# --- Адреса -------------------------------------------------------------------


async def list_addresses(
    session: AsyncSession,
    q: str | None = None,
    prefix_id: uuid.UUID | None = None,
    ci_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        select(IpAddress, Interface.name, Ci.id, Ci.name)
        .outerjoin(Interface, Interface.id == IpAddress.interface_id)
        .outerjoin(Ci, Ci.id == func.coalesce(IpAddress.ci_id, Interface.ci_id))
    )
    if prefix_id:
        stmt = stmt.where(IpAddress.prefix_id == prefix_id)
    if ci_id:
        stmt = stmt.where(
            or_(
                IpAddress.ci_id == ci_id,
                IpAddress.interface_id.in_(select(Interface.id).where(Interface.ci_id == ci_id)),
            )
        )
    if q:
        stmt = stmt.where(
            or_(
                cast(IpAddress.address, String).like(f"%{q}%"),
                func.lower(IpAddress.dns_name).like(f"%{q.lower()}%"),
            )
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = await session.execute(stmt.order_by(IpAddress.address).limit(limit).offset(offset))
    items = [
        {
            "id": address.id,
            "address": str(address.address),
            "prefix_id": address.prefix_id,
            "vrf_id": address.vrf_id,
            "interface_id": address.interface_id,
            "interface_name": interface_name,
            "ci_id": owner_id,
            "ci_name": owner_name,
            "dns_name": address.dns_name,
            "role": address.role,
            "status": address.status,
            "description": address.description,
        }
        for address, interface_name, owner_id, owner_name in rows
    ]
    return items, int(total)


async def create_address(session: AsyncSession, data: dict[str, Any]) -> IpAddress:
    payload = {k: v for k, v in data.items() if k in IP_FIELDS}
    parsed = parse_address(str(payload["address"]))
    payload["address"] = str(parsed.ip)
    if payload.get("interface_id") and await session.get(
        Interface, payload["interface_id"]
    ) is None:
        raise NotFound("Интерфейс не найден", entity_id=str(payload["interface_id"]))
    prefix = await _match_prefix(session, str(parsed.ip), payload.get("vrf_id"))
    if prefix is not None:
        payload.setdefault("prefix_id", prefix.id)
        payload.setdefault("vrf_id", prefix.vrf_id)
    status = IpStatus(payload.get("status", IpStatus.ACTIVE))
    if status != IpStatus.DEPRECATED:
        duplicate = (
            await session.execute(
                select(IpAddress.id).where(
                    IpAddress.address == payload["address"],
                    IpAddress.vrf_id.is_not_distinct_from(payload.get("vrf_id")),
                    IpAddress.status != IpStatus.DEPRECATED,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            raise Conflict(f"Адрес {parsed.ip} уже назначен в этом VRF", field="address")
    address = IpAddress(**payload)
    session.add(address)
    await session.flush()
    await _reindex_owner(session, address)
    return address


async def update_address(
    session: AsyncSession, address_id: uuid.UUID, data: dict[str, Any]
) -> IpAddress:
    address = await session.get(IpAddress, address_id)
    if address is None:
        raise NotFound("Адрес не найден", entity_id=str(address_id))
    for field in IP_FIELDS:
        if field in data:
            value = data[field]
            if field == "address" and value:
                value = str(parse_address(str(value)).ip)
            setattr(address, field, value)
    await session.flush()
    await _reindex_owner(session, address)
    return address


async def delete_address(session: AsyncSession, address_id: uuid.UUID) -> None:
    address = await session.get(IpAddress, address_id)
    if address is None:
        raise NotFound("Адрес не найден", entity_id=str(address_id))
    owner = await _owner_ci_id(session, address)
    await session.delete(address)
    await session.flush()
    if owner:
        await _reindex_ci(session, owner)


async def _match_prefix(
    session: AsyncSession, address: str, vrf_id: uuid.UUID | None
) -> Prefix | None:
    """Подбирает самую точную подсеть, в которую попадает адрес."""
    candidates = list(
        (
            await session.execute(
                select(Prefix).where(Prefix.vrf_id.is_not_distinct_from(vrf_id))
            )
        ).scalars()
    )
    host = parse_address(address).ip
    matching = [p for p in candidates if host in parse_network(str(p.cidr))]
    if not matching:
        return None
    return max(matching, key=lambda p: parse_network(str(p.cidr)).prefixlen)


async def _owner_ci_id(session: AsyncSession, address: IpAddress) -> uuid.UUID | None:
    if address.ci_id:
        return address.ci_id
    if address.interface_id:
        return (
            await session.execute(
                select(Interface.ci_id).where(Interface.id == address.interface_id)
            )
        ).scalar_one_or_none()
    return None


async def _reindex_owner(session: AsyncSession, address: IpAddress) -> None:
    owner = await _owner_ci_id(session, address)
    if owner:
        await _reindex_ci(session, owner)


async def _reindex_ci(session: AsyncSession, ci_id: uuid.UUID) -> None:
    from itms.models.network import Device
    from itms.services import device_service

    if await session.get(Device, ci_id) is not None:
        await device_service.reindex_device(session, ci_id)


async def find_by_address(session: AsyncSession, query: str) -> list[dict[str, Any]]:
    """Точный технический поиск «кому принадлежит адрес» — по индексу inet."""
    items, _ = await list_addresses(session, q=query, limit=25)
    return items
