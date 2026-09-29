from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from itms.models.enums import CiStatus, CiType, HypervisorPlatform, VmPowerState


class HostCreate(BaseModel):
    name: str | None = None
    code: str | None = None
    ci_id: uuid.UUID | None = None
    ci_type: CiType = CiType.CLUSTER
    platform: HypervisorPlatform = HypervisorPlatform.OTHER
    cpu_cores: int = Field(ge=0)
    memory_mb: int = Field(ge=0)
    storage_gb: int = Field(ge=0)


class HostUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    platform: HypervisorPlatform | None = None
    cpu_cores: int | None = Field(default=None, ge=0)
    memory_mb: int | None = Field(default=None, ge=0)
    storage_gb: int | None = Field(default=None, ge=0)


class VmCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = None
    host_id: uuid.UUID | None = None
    vcpu: int = Field(ge=1)
    memory_mb: int = Field(ge=1)
    disk_gb: int = Field(default=0, ge=0)
    guest_os: str | None = Field(default=None, max_length=128)
    power_state: VmPowerState = VmPowerState.RUNNING


class VmUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    host_id: uuid.UUID | None = None
    vcpu: int | None = Field(default=None, ge=1)
    memory_mb: int | None = Field(default=None, ge=1)
    disk_gb: int | None = Field(default=None, ge=0)
    guest_os: str | None = Field(default=None, max_length=128)
    power_state: VmPowerState | None = None


class HostRow(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    ci_type: CiType
    status: CiStatus
    platform: HypervisorPlatform
    cpu_cores: int
    memory_mb: int
    storage_gb: int
    vm_count: int
    vm_running: int
    vcpu_running: int
    memory_running_mb: int
    vcpu_allocated: int
    memory_allocated_mb: int
    disk_allocated_gb: int


class VmRow(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    status: CiStatus
    host_id: uuid.UUID | None
    host_name: str | None
    host_code: str | None
    vcpu: int
    memory_mb: int
    disk_gb: int
    guest_os: str | None
    power_state: VmPowerState


class VirtTotals(BaseModel):
    hosts: int
    vms: int
    running: int
    vcpu_running: int
    memory_running_mb: int
    vcpu_allocated: int
    memory_allocated_mb: int
    disk_allocated_gb: int
    cpu_cores: int
    memory_mb: int
    storage_gb: int


class VirtOverview(BaseModel):
    hosts: list[HostRow]
    vms: list[VmRow]
    totals: VirtTotals
