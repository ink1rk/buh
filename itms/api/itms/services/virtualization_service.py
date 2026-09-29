"""Хосты виртуализации и виртуальные машины.

Перерасход CPU и памяти не запрещается: так устроены гипервизоры. Сервис считает
занятое и отданное, а интерфейс показывает, где ёмкость уже превышена.
Запущенные машины занимают CPU и память. Диск считается у всех, кроме выведенных.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from itms.core.errors import Conflict, Invalid, NotFound
from itms.models.cmdb import Ci, CiRelation
from itms.models.enums import HOST_CI_TYPES, CiStatus, CiType, RelationType, VmPowerState
from itms.models.virtualization import ComputeHost, VirtualMachine
from itms.services import ci_service

HOST_FIELDS = ("platform", "cpu_cores", "memory_mb", "storage_gb")


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _usage(pairs: list[tuple[VirtualMachine, Ci]]) -> dict[str, int]:
    result = {
        "vm_count": 0,
        "vm_running": 0,
        "vcpu_running": 0,
        "memory_running_mb": 0,
        "vcpu_allocated": 0,
        "memory_allocated_mb": 0,
        "disk_allocated_gb": 0,
    }
    for vm, ci in pairs:
        if ci.status == CiStatus.RETIRED:
            continue
        result["vm_count"] += 1
        result["vcpu_allocated"] += vm.vcpu
        result["memory_allocated_mb"] += vm.memory_mb
        result["disk_allocated_gb"] += vm.disk_gb
        if vm.power_state == VmPowerState.RUNNING:
            result["vm_running"] += 1
            result["vcpu_running"] += vm.vcpu
            result["memory_running_mb"] += vm.memory_mb
    return result


async def _visible_hosts(session: AsyncSession) -> list[tuple[ComputeHost, Ci]]:
    rows = await session.execute(
        select(ComputeHost, Ci)
        .join(Ci, Ci.id == ComputeHost.id)
        .where(
            Ci.deleted_at.is_(None),
            Ci.archived_at.is_(None),
            Ci.status != CiStatus.RETIRED,
        )
        .order_by(Ci.name)
    )
    return list(rows.all())


async def _visible_vms(session: AsyncSession) -> list[tuple[VirtualMachine, Ci]]:
    rows = await session.execute(
        select(VirtualMachine, Ci)
        .join(Ci, Ci.id == VirtualMachine.id)
        .where(Ci.deleted_at.is_(None), Ci.archived_at.is_(None))
        .order_by(Ci.name)
    )
    return list(rows.all())


async def overview(session: AsyncSession) -> dict[str, Any]:
    hosts = await _visible_hosts(session)
    vms = await _visible_vms(session)
    host_ids = {host.id for host, _ in hosts}
    names: dict[uuid.UUID, Ci] = {host.id: ci for host, ci in hosts}
    missing = {vm.host_id for vm, _ in vms if vm.host_id and vm.host_id not in names}
    if missing:
        extra = await session.execute(select(Ci).where(Ci.id.in_(missing)))
        for ci in extra.scalars():
            names[ci.id] = ci

    grouped: dict[uuid.UUID, list[tuple[VirtualMachine, Ci]]] = {}
    for vm, ci in vms:
        if vm.host_id and vm.host_id in host_ids:
            grouped.setdefault(vm.host_id, []).append((vm, ci))

    host_rows = []
    capacity = {"cpu_cores": 0, "memory_mb": 0, "storage_gb": 0}
    for host, ci in hosts:
        usage = _usage(grouped.get(host.id, []))
        capacity["cpu_cores"] += host.cpu_cores
        capacity["memory_mb"] += host.memory_mb
        capacity["storage_gb"] += host.storage_gb
        host_rows.append(
            {
                "id": host.id,
                "name": ci.name,
                "code": ci.code,
                "ci_type": ci.ci_type,
                "status": ci.status,
                "platform": host.platform,
                "cpu_cores": host.cpu_cores,
                "memory_mb": host.memory_mb,
                "storage_gb": host.storage_gb,
                **usage,
            }
        )

    vm_rows = []
    for vm, ci in vms:
        host_ci = names.get(vm.host_id) if vm.host_id else None
        vm_rows.append(
            {
                "id": vm.id,
                "name": ci.name,
                "code": ci.code,
                "status": ci.status,
                "host_id": vm.host_id if host_ci else None,
                "host_name": host_ci.name if host_ci else None,
                "host_code": host_ci.code if host_ci else None,
                "vcpu": vm.vcpu,
                "memory_mb": vm.memory_mb,
                "disk_gb": vm.disk_gb,
                "guest_os": vm.guest_os,
                "power_state": vm.power_state,
            }
        )

    fleet = _usage(vms)
    return {
        "hosts": host_rows,
        "vms": vm_rows,
        "totals": {
            "hosts": len(host_rows),
            "vms": fleet["vm_count"],
            "running": fleet["vm_running"],
            **{key: fleet[key] for key in fleet if key not in {"vm_count", "vm_running"}},
            **capacity,
        },
    }


async def _require_host(session: AsyncSession, host_id: uuid.UUID) -> ComputeHost:
    host = await session.get(ComputeHost, host_id)
    if host is None:
        raise NotFound("Хост виртуализации не найден", entity_id=str(host_id))
    ci = await ci_service.get_ci(session, host_id)
    if ci.status == CiStatus.RETIRED:
        raise Invalid("Нельзя размещать машины на выведенном хосте", code_hint="host_retired")
    return host


async def create_host(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    ci_id = data.get("ci_id")
    if ci_id:
        ci = await ci_service.get_ci(session, ci_id)
        if ci.ci_type not in HOST_CI_TYPES:
            raise Invalid(
                "Хостом виртуализации может быть кластер или оборудование",
                code_hint="not_a_host",
            )
        if await session.get(ComputeHost, ci.id):
            raise Conflict("У объекта уже есть профиль виртуализации", code_hint="host_exists")
    else:
        ci_type = CiType(data.get("ci_type") or CiType.CLUSTER)
        if ci_type not in HOST_CI_TYPES:
            raise Invalid(
                "Хостом виртуализации может быть кластер или оборудование",
                code_hint="not_a_host",
            )
        name = _blank(data.get("name"))
        if not name:
            raise Invalid("Укажите имя хоста", code_hint="name_required")
        ci = await ci_service.create_ci(
            session,
            {
                "ci_type": ci_type,
                "name": name,
                "code": _blank(data.get("code")),
                "status": CiStatus.ACTIVE,
            },
        )
    host = ComputeHost(
        id=ci.id,
        platform=data.get("platform") or "OTHER",
        cpu_cores=int(data["cpu_cores"]),
        memory_mb=int(data["memory_mb"]),
        storage_gb=int(data["storage_gb"]),
    )
    session.add(host)
    await session.flush()
    return await overview(session)


async def update_host(
    session: AsyncSession, host_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    host = await session.get(ComputeHost, host_id)
    if host is None:
        raise NotFound("Хост виртуализации не найден", entity_id=str(host_id))
    ci_fields = {}
    if "name" in data:
        name = _blank(data.get("name"))
        if not name:
            raise Invalid("Укажите имя хоста", code_hint="name_required")
        ci_fields["name"] = name
    if "code" in data:
        ci_fields["code"] = _blank(data.get("code"))
    if ci_fields:
        await ci_service.update_ci(session, host_id, ci_fields)
    for field in HOST_FIELDS:
        if field in data and data[field] is not None:
            setattr(host, field, data[field])
    await session.flush()
    return await overview(session)


async def _sync_runs_on(
    session: AsyncSession,
    vm_id: uuid.UUID,
    old_host_id: uuid.UUID | None,
    new_host_id: uuid.UUID | None,
) -> None:
    if old_host_id == new_host_id:
        return
    if old_host_id is not None:
        relation = (
            await session.execute(
                select(CiRelation).where(
                    CiRelation.source_ci_id == vm_id,
                    CiRelation.target_ci_id == old_host_id,
                    CiRelation.rel_type == RelationType.RUNS_ON,
                )
            )
        ).scalar_one_or_none()
        if relation is not None:
            await session.delete(relation)
            await session.flush()
    if new_host_id is None:
        return
    existing = (
        await session.execute(
            select(CiRelation.id).where(
                CiRelation.source_ci_id == vm_id,
                CiRelation.target_ci_id == new_host_id,
                CiRelation.rel_type == RelationType.RUNS_ON,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        await ci_service.create_relation(
            session,
            {
                "source_ci_id": vm_id,
                "target_ci_id": new_host_id,
                "rel_type": RelationType.RUNS_ON,
            },
        )


async def create_vm(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    name = _blank(data.get("name"))
    if not name:
        raise Invalid("Укажите имя виртуальной машины", code_hint="name_required")
    host_id = data.get("host_id")
    if host_id is not None:
        await _require_host(session, host_id)
    ci = await ci_service.create_ci(
        session,
        {
            "ci_type": CiType.VM,
            "name": name,
            "code": _blank(data.get("code")),
            "status": CiStatus.ACTIVE,
        },
    )
    vm = VirtualMachine(
        id=ci.id,
        host_id=host_id,
        vcpu=int(data["vcpu"]),
        memory_mb=int(data["memory_mb"]),
        disk_gb=int(data.get("disk_gb") or 0),
        guest_os=_blank(data.get("guest_os")),
        power_state=data.get("power_state") or VmPowerState.RUNNING,
    )
    session.add(vm)
    await session.flush()
    await _sync_runs_on(session, vm.id, None, host_id)
    return await overview(session)


async def update_vm(
    session: AsyncSession, vm_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    vm = await session.get(VirtualMachine, vm_id)
    if vm is None:
        raise NotFound("Виртуальная машина не найдена", entity_id=str(vm_id))
    ci_fields = {}
    if "name" in data:
        name = _blank(data.get("name"))
        if not name:
            raise Invalid("Укажите имя виртуальной машины", code_hint="name_required")
        ci_fields["name"] = name
    if "code" in data:
        ci_fields["code"] = _blank(data.get("code"))
    if ci_fields:
        await ci_service.update_ci(session, vm_id, ci_fields)
    old_host = vm.host_id
    if "host_id" in data:
        new_host = data["host_id"]
        if new_host is not None:
            await _require_host(session, new_host)
        vm.host_id = new_host
    else:
        new_host = old_host
    if "guest_os" in data:
        vm.guest_os = _blank(data["guest_os"])
    for field in ("vcpu", "memory_mb", "disk_gb", "power_state"):
        if field in data and data[field] is not None:
            setattr(vm, field, data[field])
    await session.flush()
    if "host_id" in data:
        await _sync_runs_on(session, vm.id, old_host, new_host)
    return await overview(session)
