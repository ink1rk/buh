from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import (
    CableCategory,
    CableMedium,
    CiStatus,
    ConnectionStatus,
    Criticality,
    DeviceRole,
    InterfaceType,
    IpRole,
    IpStatus,
    PanelSide,
    VlanMode,
)


def _as_text(value: Any) -> Any:
    """inet/cidr/macaddr приходят из драйвера объектами — наружу отдаём строку."""
    return value if value is None or isinstance(value, str) else str(value)


NetText = Annotated[str | None, BeforeValidator(_as_text)]


# --- Каталог ------------------------------------------------------------------


class ManufacturerWrite(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    support_url: str | None = None
    notes: str | None = None


class ManufacturerRead(ORMModel):
    id: uuid.UUID
    name: str
    support_url: str | None
    notes: str | None


class PortTemplateWrite(BaseModel):
    name_pattern: str = Field(min_length=1, max_length=64)
    count: int = Field(default=1, ge=1, le=512)
    start_index: int = Field(default=1, ge=0)
    interface_type: InterfaceType
    speed_mbps: int | None = None
    poe_capable: bool = False
    position: int = 100


class PortTemplateRead(ORMModel):
    id: uuid.UUID
    name_pattern: str
    count: int
    start_index: int
    interface_type: InterfaceType
    speed_mbps: int | None
    poe_capable: bool
    position: int


class DeviceModelWrite(BaseModel):
    manufacturer_id: uuid.UUID
    model: str = Field(min_length=1, max_length=128)
    part_number: str | None = None
    default_role: DeviceRole = DeviceRole.OTHER
    u_height: float = Field(default=1, ge=0, le=60)
    is_full_depth: bool = True
    depth_mm: int | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    psu_count: int = Field(default=1, ge=0, le=16)
    power_nameplate_w: int | None = Field(default=None, ge=0)
    power_max_w: int | None = Field(default=None, ge=0)
    power_factor: float | None = Field(default=None, gt=0, le=1)
    utilization_factor: float | None = Field(default=None, gt=0, le=1)
    airflow: str | None = None
    notes: str | None = None
    port_templates: list[PortTemplateWrite] = Field(default_factory=list)


class DeviceModelUpdate(BaseModel):
    manufacturer_id: uuid.UUID | None = None
    model: str | None = None
    part_number: str | None = None
    default_role: DeviceRole | None = None
    u_height: float | None = None
    is_full_depth: bool | None = None
    depth_mm: int | None = None
    weight_kg: float | None = None
    psu_count: int | None = None
    power_nameplate_w: int | None = None
    power_max_w: int | None = None
    power_factor: float | None = None
    utilization_factor: float | None = None
    airflow: str | None = None
    notes: str | None = None


class DeviceModelRead(ORMModel):
    id: uuid.UUID
    manufacturer_id: uuid.UUID
    manufacturer: ManufacturerRead
    model: str
    part_number: str | None
    default_role: DeviceRole
    u_height: float
    is_full_depth: bool
    depth_mm: int | None
    weight_kg: float | None
    psu_count: int
    power_nameplate_w: int | None
    power_max_w: int | None
    power_factor: float | None
    utilization_factor: float | None
    airflow: str | None
    notes: str | None
    port_templates: list[PortTemplateRead] = Field(default_factory=list)


# --- Устройства ---------------------------------------------------------------


class DeviceWrite(BaseModel):
    device_model_id: uuid.UUID | None = None
    device_role: DeviceRole = DeviceRole.OTHER
    asset_tag: str | None = None
    hostname: str | None = Field(default=None, max_length=255)
    mgmt_ip: str | None = None
    mgmt_mac: str | None = None
    firmware: str | None = None
    os_version: str | None = None
    purchase_date: date | None = None
    warranty_until: date | None = None
    psu_count: int = Field(default=1, ge=0, le=16)
    power_nameplate_w: int | None = Field(default=None, ge=0)
    power_max_w: int | None = Field(default=None, ge=0)
    notes: str | None = None


class DeviceRead(ORMModel):
    id: uuid.UUID
    device_model_id: uuid.UUID | None
    model: DeviceModelRead | None = None
    device_role: DeviceRole
    asset_tag: str | None
    hostname: str | None
    mgmt_ip: NetText = None
    mgmt_mac: NetText = None
    firmware: str | None
    os_version: str | None
    purchase_date: date | None
    warranty_until: date | None
    psu_count: int
    power_nameplate_w: int | None
    power_max_w: int | None
    notes: str | None


class DeviceRow(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None
    status: CiStatus
    criticality: Criticality
    location_id: uuid.UUID | None
    device_role: DeviceRole
    hostname: str | None
    mgmt_ip: str | None
    serial_number: str | None
    asset_tag: str | None
    warranty_until: date | None
    model_label: str | None


class PortUsage(BaseModel):
    total: int
    free: int
    used: int


# --- Интерфейсы ---------------------------------------------------------------


class InterfaceVlanWrite(BaseModel):
    vlan_id: uuid.UUID
    mode: VlanMode


class InterfaceVlanRead(BaseModel):
    vlan_id: uuid.UUID
    vid: int
    name: str
    mode: VlanMode


class InterfaceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    position: int | None = None
    interface_type: InterfaceType
    medium: CableMedium | None = None
    speed_mbps: int | None = Field(default=None, ge=0)
    duplex: str | None = None
    mac: str | None = None
    description: str = ""
    purpose: str | None = None
    admin_enabled: bool = True
    oper_status: str = "UNKNOWN"
    is_management: bool = False
    poe_mode: str | None = None
    mtu: int | None = None
    lag_parent_id: uuid.UUID | None = None
    panel_side: PanelSide | None = None
    paired_interface_id: uuid.UUID | None = None
    vlans: list[InterfaceVlanWrite] | None = None


class InterfaceUpdate(BaseModel):
    name: str | None = None
    position: int | None = None
    interface_type: InterfaceType | None = None
    medium: CableMedium | None = None
    speed_mbps: int | None = None
    duplex: str | None = None
    mac: str | None = None
    description: str | None = None
    purpose: str | None = None
    admin_enabled: bool | None = None
    oper_status: str | None = None
    is_management: bool | None = None
    poe_mode: str | None = None
    mtu: int | None = None
    lag_parent_id: uuid.UUID | None = None
    panel_side: PanelSide | None = None
    paired_interface_id: uuid.UUID | None = None
    vlans: list[InterfaceVlanWrite] | None = None


class EndpointRef(BaseModel):
    interface_id: uuid.UUID
    interface_name: str
    ci_id: uuid.UUID
    ci_name: str | None = None


class ConnectionBrief(BaseModel):
    id: uuid.UUID
    label: str | None
    status: ConnectionStatus
    medium: CableMedium
    length_m: float | None
    peer: EndpointRef | None = None


class InterfaceRow(BaseModel):
    id: uuid.UUID
    ci_id: uuid.UUID
    name: str
    position: int | None
    interface_type: InterfaceType
    medium: CableMedium | None
    speed_mbps: int | None
    mac: NetText = None
    description: str
    purpose: str | None
    admin_enabled: bool
    oper_status: str
    is_management: bool
    mtu: int | None
    panel_side: PanelSide | None
    paired_interface_id: uuid.UUID | None
    lag_parent_id: uuid.UUID | None
    ip_addresses: list[str] = Field(default_factory=list)
    vlans: list[InterfaceVlanRead] = Field(default_factory=list)
    connection: ConnectionBrief | None = None


# --- Кабели -------------------------------------------------------------------


class ConnectionCreate(BaseModel):
    a_interface_id: uuid.UUID
    b_interface_id: uuid.UUID
    medium: CableMedium
    category: CableCategory | None = None
    label: str | None = Field(default=None, max_length=64)
    connector_a: str | None = None
    connector_b: str | None = None
    length_m: float | None = Field(default=None, ge=0)
    speed_mbps: int | None = Field(default=None, ge=0)
    color: str | None = None
    status: ConnectionStatus = ConnectionStatus.ACTIVE
    route_id: uuid.UUID | None = None
    is_redundant: bool = False
    redundancy_group: str | None = None
    installed_on: date | None = None
    tested_on: date | None = None
    test_result: str | None = None
    description: str = ""


class ConnectionUpdate(BaseModel):
    label: str | None = None
    medium: CableMedium | None = None
    category: CableCategory | None = None
    connector_a: str | None = None
    connector_b: str | None = None
    length_m: float | None = None
    speed_mbps: int | None = None
    color: str | None = None
    status: ConnectionStatus | None = None
    route_id: uuid.UUID | None = None
    is_redundant: bool | None = None
    redundancy_group: str | None = None
    installed_on: date | None = None
    tested_on: date | None = None
    test_result: str | None = None
    description: str | None = None


class ConnectionRow(BaseModel):
    id: uuid.UUID
    label: str | None
    medium: CableMedium
    category: CableCategory | None
    status: ConnectionStatus
    length_m: float | None
    speed_mbps: int | None
    color: str | None
    is_redundant: bool
    redundancy_group: str | None
    route_id: uuid.UUID | None
    installed_on: date | None
    description: str
    a_end: EndpointRef | None = None
    b_end: EndpointRef | None = None


class ConnectionResult(BaseModel):
    """Кабель сохранён; предупреждения не блокируют, но их важно показать."""

    connection: ConnectionRow
    warnings: list[str] = Field(default_factory=list)


class TraceSegment(BaseModel):
    connection_id: uuid.UUID
    label: str | None
    length_m: float | None


class TracePassThrough(BaseModel):
    ci_id: uuid.UUID
    ci_name: str | None


class TraceResult(BaseModel):
    start: EndpointRef
    endpoint: EndpointRef | None
    segments: list[TraceSegment]
    passed_through: list[TracePassThrough]
    total_length_m: float | None
    is_direct: bool
    truncated: bool


class RedundancyMember(BaseModel):
    id: uuid.UUID
    label: str | None
    status: ConnectionStatus


class RedundancyGroup(BaseModel):
    group: str
    members: list[RedundancyMember]
    issues: list[str]


class FreePortsRow(BaseModel):
    ci_id: uuid.UUID
    name: str
    device_role: DeviceRole
    total: int
    free: int


class CableRouteWrite(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    route_type: str | None = None
    from_location_id: uuid.UUID | None = None
    to_location_id: uuid.UUID | None = None
    length_m: float | None = None
    capacity: int | None = None
    notes: str | None = None


class CableRouteRead(ORMModel):
    id: uuid.UUID
    name: str
    route_type: str | None
    from_location_id: uuid.UUID | None
    to_location_id: uuid.UUID | None
    length_m: float | None
    capacity: int | None
    notes: str | None


# --- Адресация ----------------------------------------------------------------


class VrfWrite(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    rd: str | None = None
    description: str | None = None


class VrfRead(ORMModel):
    id: uuid.UUID
    name: str
    rd: str | None
    description: str | None


class VlanWrite(BaseModel):
    vid: int = Field(ge=1, le=4094)
    name: str = Field(min_length=1, max_length=128)
    site_id: uuid.UUID | None = None
    purpose: str | None = None
    description: str | None = None


class VlanUpdate(BaseModel):
    vid: int | None = Field(default=None, ge=1, le=4094)
    name: str | None = None
    site_id: uuid.UUID | None = None
    purpose: str | None = None
    description: str | None = None


class VlanRow(BaseModel):
    id: uuid.UUID
    vid: int
    name: str
    site_id: uuid.UUID | None
    site_name: str | None
    purpose: str | None
    description: str | None
    prefix_count: int


class PrefixWrite(BaseModel):
    cidr: str = Field(min_length=3, max_length=64)
    vrf_id: uuid.UUID | None = None
    vlan_id: uuid.UUID | None = None
    gateway: str | None = None
    dhcp_from: str | None = None
    dhcp_to: str | None = None
    site_id: uuid.UUID | None = None
    description: str | None = None


class PrefixUpdate(BaseModel):
    vrf_id: uuid.UUID | None = None
    vlan_id: uuid.UUID | None = None
    gateway: str | None = None
    dhcp_from: str | None = None
    dhcp_to: str | None = None
    site_id: uuid.UUID | None = None
    description: str | None = None


class PrefixRow(BaseModel):
    id: uuid.UUID
    cidr: str
    version: int
    vrf_id: uuid.UUID | None
    vrf_name: str | None
    vlan_id: uuid.UUID | None
    vlan_label: str | None
    gateway: str | None
    site_id: uuid.UUID | None
    description: str | None
    usable_total: int
    used: int
    free: int
    utilisation_pct: float


class PrefixCapacityRead(BaseModel):
    usable_total: int
    used: int
    free: int
    utilisation_pct: float
    network_address: str
    broadcast_address: str | None
    netmask: str


class IpAddressWrite(BaseModel):
    address: str = Field(min_length=2, max_length=64)
    vrf_id: uuid.UUID | None = None
    prefix_id: uuid.UUID | None = None
    interface_id: uuid.UUID | None = None
    ci_id: uuid.UUID | None = None
    dns_name: str | None = None
    role: IpRole = IpRole.PRIMARY
    status: IpStatus = IpStatus.ACTIVE
    description: str | None = None


class IpAddressUpdate(BaseModel):
    address: str | None = None
    vrf_id: uuid.UUID | None = None
    prefix_id: uuid.UUID | None = None
    interface_id: uuid.UUID | None = None
    ci_id: uuid.UUID | None = None
    dns_name: str | None = None
    role: IpRole | None = None
    status: IpStatus | None = None
    description: str | None = None


class IpAddressRow(BaseModel):
    id: uuid.UUID
    address: str
    prefix_id: uuid.UUID | None
    vrf_id: uuid.UUID | None
    interface_id: uuid.UUID | None
    interface_name: str | None
    ci_id: uuid.UUID | None
    ci_name: str | None
    dns_name: str | None
    role: IpRole
    status: IpStatus
    description: str | None


class PrefixDetail(BaseModel):
    prefix: PrefixRow
    capacity: PrefixCapacityRead
    next_free: list[str]
    addresses: list[IpAddressRow]


class WarrantyRow(BaseModel):
    id: uuid.UUID
    name: str
    warranty_until: date
    device_role: DeviceRole


class IpAddressRead(ORMModel):
    id: uuid.UUID
    address: NetText = None
    vrf_id: uuid.UUID | None
    prefix_id: uuid.UUID | None
    interface_id: uuid.UUID | None
    ci_id: uuid.UUID | None
    dns_name: str | None
    role: IpRole
    status: IpStatus
    description: str | None
    created_at: datetime
