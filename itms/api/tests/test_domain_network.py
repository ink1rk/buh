"""Unit-тесты инженерных правил сети и адресации — без базы и HTTP."""

from __future__ import annotations

import uuid

import pytest

from itms.core.errors import Invalid
from itms.domain.ipam import (
    address_conflicts,
    ensure_address_in_prefix,
    next_free_addresses,
    parse_network,
    prefix_capacity,
    usable_hosts,
)
from itms.domain.network import (
    InterfaceFacts,
    LinkSegment,
    expand_port_template,
    free_port_summary,
    normalize_mac,
    redundancy_violations,
    trace_link,
    validate_connection,
)
from itms.models.enums import (
    PATCHABLE_INTERFACE_TYPES,
    CableMedium,
    DeviceRole,
    InterfaceType,
)


def test_port_template_expands_with_padding() -> None:
    assert expand_port_template("Gi1/0/{n}", 3) == [
        ("Gi1/0/1", 1),
        ("Gi1/0/2", 2),
        ("Gi1/0/3", 3),
    ]
    assert expand_port_template("Port-{n:03}", 2, start_index=9)[0] == ("Port-009", 9)


def test_port_template_requires_placeholder_for_many_ports() -> None:
    assert expand_port_template("Console", 1) == [("Console", 1)]
    with pytest.raises(Invalid):
        expand_port_template("Console", 4)


def test_mac_is_normalized_from_any_format() -> None:
    assert normalize_mac("00-1A-2b-3C-4d-5E") == "00:1a:2b:3c:4d:5e"
    assert normalize_mac("001a.2b3c.4d5e") == "00:1a:2b:3c:4d:5e"
    assert normalize_mac(None) is None
    with pytest.raises(Invalid):
        normalize_mac("не-mac")


def _port(
    name: str,
    interface_type: InterfaceType = InterfaceType.SFP_PLUS,
    *,
    speed: int | None = 10000,
    occupied: bool = False,
    role: DeviceRole = DeviceRole.L3_SWITCH,
    paired: uuid.UUID | None = None,
) -> InterfaceFacts:
    return InterfaceFacts(
        id=uuid.uuid4(),
        ci_id=uuid.uuid4(),
        name=name,
        interface_type=interface_type,
        speed_mbps=speed,
        device_role=role,
        paired_interface_id=paired,
        occupied=occupied,
    )


def test_connection_to_occupied_port_is_rejected() -> None:
    with pytest.raises(Invalid) as exc:
        validate_connection(_port("Te1/0/1"), _port("Te1/0/2", occupied=True), CableMedium.FIBER)
    assert exc.value.details["code_hint"] == "port_occupied"


def test_connection_to_logical_interface_is_rejected() -> None:
    with pytest.raises(Invalid) as exc:
        validate_connection(
            _port("Po1", InterfaceType.LAG), _port("Te1/0/2"), CableMedium.FIBER
        )
    assert exc.value.details["code_hint"] == "logical_interface"


def test_medium_and_speed_mismatch_are_warnings_not_errors() -> None:
    check = validate_connection(
        _port("Gi0/1", InterfaceType.RJ45, speed=1000),
        _port("Te1/0/2", InterfaceType.SFP_PLUS, speed=10000),
        CableMedium.FIBER,
        speed_mbps=10000,
    )
    assert check.warnings
    assert any("RJ45" in message for message in check.warnings)
    assert any("Скорости портов различаются" in message for message in check.warnings)


def test_trace_goes_through_patch_panel_to_real_endpoint() -> None:
    server_port = _port("eth0", InterfaceType.RJ45, role=DeviceRole.SERVER)
    panel_front = _port("1", InterfaceType.RJ45, role=DeviceRole.PATCH_PANEL)
    panel_rear = _port("1R", InterfaceType.RJ45, role=DeviceRole.PATCH_PANEL)
    panel_front = InterfaceFacts(
        id=panel_front.id,
        ci_id=panel_front.ci_id,
        name=panel_front.name,
        interface_type=panel_front.interface_type,
        device_role=DeviceRole.PATCH_PANEL,
        paired_interface_id=panel_rear.id,
    )
    switch_port = _port("Gi1/0/5", InterfaceType.RJ45, role=DeviceRole.L2_SWITCH)

    segments = {
        server_port.id: LinkSegment(uuid.uuid4(), "патч-корд", 2.0, server_port.id,
                                    panel_front.id),
        panel_front.id: LinkSegment(uuid.uuid4(), "патч-корд", 2.0, server_port.id,
                                    panel_front.id),
        panel_rear.id: LinkSegment(uuid.uuid4(), "магистраль", 35.5, panel_rear.id,
                                   switch_port.id),
        switch_port.id: LinkSegment(uuid.uuid4(), "магистраль", 35.5, panel_rear.id,
                                    switch_port.id),
    }
    facts = {
        item.id: item for item in (server_port, panel_front, panel_rear, switch_port)
    }
    used: set[uuid.UUID] = set()

    def connection_of(interface_id: uuid.UUID) -> LinkSegment | None:
        segment = segments.get(interface_id)
        if segment is None or segment.connection_id in used:
            return None
        used.add(segment.connection_id)
        return segment

    path = trace_link(server_port, connection_of, facts.get)
    assert len(path.segments) == 2
    assert path.endpoint_interface_id == switch_port.id
    assert path.passed_through == [panel_front.ci_id]
    assert path.total_length_m == 37.5
    assert path.is_direct is False


def test_free_port_summary_counts_only_physical_ports() -> None:
    ports = [
        _port("Gi0/1", InterfaceType.RJ45),
        _port("Gi0/2", InterfaceType.RJ45, occupied=True),
        _port("Po1", InterfaceType.LAG),
    ]
    assert free_port_summary(ports, PATCHABLE_INTERFACE_TYPES) == (2, 1)


def test_redundancy_group_on_single_route_is_flagged() -> None:
    issues = redundancy_violations(
        "LAG-CORE",
        [(uuid.uuid4(), "Лоток A2", "ACTIVE"), (uuid.uuid4(), "Лоток A2", "ACTIVE")],
    )
    assert any("одной трассе" in issue for issue in issues)


def test_prefix_capacity_excludes_network_and_broadcast() -> None:
    capacity = prefix_capacity("10.20.5.0/24", ["10.20.5.1", "10.20.5.17"])
    assert capacity.usable_total == 254
    assert capacity.used == 2
    assert capacity.free == 252
    assert capacity.broadcast_address == "10.20.5.255"


def test_point_to_point_prefixes_have_no_reserved_addresses() -> None:
    assert usable_hosts(parse_network("10.0.0.0/31")) == 2
    assert usable_hosts(parse_network("10.0.0.1/32")) == 1


def test_next_free_addresses_skips_gateway_and_taken() -> None:
    free = next_free_addresses("10.20.5.0/24", ["10.20.5.2"], limit=3, skip=["10.20.5.1"])
    assert free == ["10.20.5.3", "10.20.5.4", "10.20.5.5"]


def test_address_outside_prefix_is_rejected() -> None:
    ensure_address_in_prefix("10.20.5.17", "10.20.5.0/24")
    with pytest.raises(Invalid) as exc:
        ensure_address_in_prefix("10.20.6.17", "10.20.5.0/24")
    assert exc.value.details["code_hint"] == "ip_outside_prefix"


def test_duplicate_addresses_are_reported_per_vrf() -> None:
    conflicts = address_conflicts(
        [("10.20.5.17", None), ("10.20.5.17", None), ("10.20.5.17", "mgmt")]
    )
    assert conflicts == ["10.20.5.17"]
