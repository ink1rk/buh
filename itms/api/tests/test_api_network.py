"""API-тесты сетевого слоя на настоящем PostgreSQL."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _manufacturer(client: AsyncClient, api: str, name: str = "Cisco") -> str:
    response = await client.post(f"{api}/catalog/manufacturers", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _model(
    client: AsyncClient,
    api: str,
    manufacturer_id: str,
    *,
    model: str = "C9300-48P",
    templates: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "manufacturer_id": manufacturer_id,
        "model": model,
        "default_role": "L3_SWITCH",
        "u_height": 1,
        "psu_count": 2,
        "power_nameplate_w": 350,
        "power_max_w": 1100,
        "port_templates": templates
        or [
            {
                "name_pattern": "Gi1/0/{n}",
                "count": 4,
                "interface_type": "RJ45",
                "speed_mbps": 1000,
                "poe_capable": True,
            },
            {
                "name_pattern": "Te1/1/{n}",
                "count": 2,
                "interface_type": "SFP_PLUS",
                "speed_mbps": 10000,
                "position": 200,
            },
        ],
    }
    response = await client.post(f"{api}/catalog/models", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _ci(client: AsyncClient, api: str, name: str, code: str) -> str:
    response = await client.post(
        f"{api}/ci", json={"ci_type": "DEVICE", "name": name, "code": code}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _device(
    client: AsyncClient, api: str, ci_id: str, *, model_id: str | None = None, **extra: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {"device_role": "L3_SWITCH", **extra}
    if model_id:
        payload["device_model_id"] = model_id
    response = await client.put(f"{api}/devices/{ci_id}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def _ports(client: AsyncClient, api: str, ci_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"{api}/devices/{ci_id}/interfaces")
    assert response.status_code == 200, response.text
    return response.json()


async def test_model_templates_create_device_ports(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    ci_id = await _ci(client, api, "Коммутатор ядра", "SW-CORE-01")
    await _device(client, api, ci_id, model_id=model_id, hostname="sw-core-01")

    ports = await _ports(client, api, ci_id)
    names = [port["name"] for port in ports]
    assert names == ["Gi1/0/1", "Gi1/0/2", "Gi1/0/3", "Gi1/0/4", "Te1/1/1", "Te1/1/2"]
    assert all(port["connection"] is None for port in ports)

    usage = (await client.get(f"{api}/devices/{ci_id}/ports")).json()
    assert usage == {"total": 6, "free": 6, "used": 0}


async def test_duplicate_model_in_catalog_is_rejected(client: AsyncClient, api: str) -> None:
    manufacturer_id = await _manufacturer(client, api)
    await _model(client, api, manufacturer_id, templates=[])
    response = await client.post(
        f"{api}/catalog/models",
        json={"manufacturer_id": manufacturer_id, "model": "C9300-48P"},
    )
    assert response.status_code == 409


async def test_model_with_devices_cannot_be_deleted(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api), templates=[])
    ci_id = await _ci(client, api, "Коммутатор доступа", "SW-ACC-01")
    await _device(client, api, ci_id, model_id=model_id)

    response = await client.delete(f"{api}/catalog/models/{model_id}")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["count"] == 1


async def test_cable_occupies_port_and_second_cable_is_rejected(
    client: AsyncClient, api: str
) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    core_id = await _ci(client, api, "Коммутатор ядра", "SW-CORE-01")
    access_id = await _ci(client, api, "Коммутатор доступа", "SW-ACC-01")
    spare_id = await _ci(client, api, "Резервный коммутатор", "SW-ACC-02")
    for ci_id in (core_id, access_id, spare_id):
        await _device(client, api, ci_id, model_id=model_id)

    core_port = (await _ports(client, api, core_id))[4]
    access_port = (await _ports(client, api, access_id))[4]
    spare_port = (await _ports(client, api, spare_id))[4]

    created = await client.post(
        f"{api}/network/connections",
        json={
            "a_interface_id": core_port["id"],
            "b_interface_id": access_port["id"],
            "medium": "FIBER",
            "category": "OM4",
            "label": "F-A2-14",
            "length_m": 35.5,
            "speed_mbps": 10000,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["warnings"] == []
    assert body["connection"]["a_end"]["ci_name"] == "Коммутатор ядра"

    ports = await _ports(client, api, core_id)
    linked = next(port for port in ports if port["id"] == core_port["id"])
    assert linked["connection"]["label"] == "F-A2-14"
    assert linked["connection"]["peer"]["ci_name"] == "Коммутатор доступа"

    second = await client.post(
        f"{api}/network/connections",
        json={
            "a_interface_id": core_port["id"],
            "b_interface_id": spare_port["id"],
            "medium": "FIBER",
        },
    )
    assert second.status_code == 422
    assert second.json()["error"]["details"]["code_hint"] == "port_occupied"


async def test_medium_mismatch_returns_warning_but_saves(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    left = await _ci(client, api, "Сервер", "SRV-01")
    right = await _ci(client, api, "Коммутатор", "SW-01")
    for ci_id in (left, right):
        await _device(client, api, ci_id, model_id=model_id)

    copper_port = (await _ports(client, api, left))[0]
    fiber_port = (await _ports(client, api, right))[4]

    response = await client.post(
        f"{api}/network/connections",
        json={
            "a_interface_id": copper_port["id"],
            "b_interface_id": fiber_port["id"],
            "medium": "FIBER",
            "speed_mbps": 10000,
        },
    )
    assert response.status_code == 201, response.text
    warnings = response.json()["warnings"]
    assert any("RJ45" in warning for warning in warnings)
    assert any("возможностей портов" in warning for warning in warnings)


async def test_trace_passes_through_patch_panel(client: AsyncClient, api: str) -> None:
    manufacturer_id = await _manufacturer(client, api)
    switch_model = await _model(client, api, manufacturer_id, model="SW", templates=[
        {"name_pattern": "Gi1/0/{n}", "count": 2, "interface_type": "RJ45", "speed_mbps": 1000}
    ])
    server_id = await _ci(client, api, "Сервер 1С", "SRV-1C-01")
    panel_id = await _ci(client, api, "Патч-панель R1", "PP-R1")
    switch_id = await _ci(client, api, "Коммутатор доступа", "SW-ACC-02")

    await _device(client, api, server_id, model_id=switch_model, device_role="SERVER")
    await _device(client, api, switch_id, model_id=switch_model, device_role="L2_SWITCH")
    await _device(client, api, panel_id, device_role="PATCH_PANEL")

    front = (
        await client.post(
            f"{api}/devices/{panel_id}/interfaces",
            json={"name": "1F", "interface_type": "RJ45", "panel_side": "FRONT", "position": 1},
        )
    ).json()
    rear = (
        await client.post(
            f"{api}/devices/{panel_id}/interfaces",
            json={"name": "1R", "interface_type": "RJ45", "panel_side": "REAR", "position": 101},
        )
    ).json()
    front_port = next(port for port in front if port["name"] == "1F")
    rear_port = next(port for port in rear if port["name"] == "1R")

    for source, target in ((front_port["id"], rear_port["id"]),
                           (rear_port["id"], front_port["id"])):
        patched = await client.patch(
            f"{api}/interfaces/{source}", json={"paired_interface_id": target}
        )
        assert patched.status_code == 200, patched.text

    server_port = (await _ports(client, api, server_id))[0]
    switch_port = (await _ports(client, api, switch_id))[0]

    assert (
        await client.post(
            f"{api}/network/connections",
            json={
                "a_interface_id": server_port["id"],
                "b_interface_id": front_port["id"],
                "medium": "COPPER",
                "length_m": 2,
                "label": "патч-корд",
            },
        )
    ).status_code == 201
    assert (
        await client.post(
            f"{api}/network/connections",
            json={
                "a_interface_id": rear_port["id"],
                "b_interface_id": switch_port["id"],
                "medium": "COPPER",
                "length_m": 35.5,
                "label": "магистраль",
            },
        )
    ).status_code == 201

    trace = await client.get(f"{api}/network/interfaces/{server_port['id']}/trace")
    assert trace.status_code == 200, trace.text
    result = trace.json()
    assert result["endpoint"]["ci_name"] == "Коммутатор доступа"
    assert len(result["segments"]) == 2
    assert result["total_length_m"] == 37.5
    assert [item["ci_name"] for item in result["passed_through"]] == ["Патч-панель R1"]


async def test_free_ports_report_reflects_cabling(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    left = await _ci(client, api, "Коммутатор A", "SW-A")
    right = await _ci(client, api, "Коммутатор B", "SW-B")
    for ci_id in (left, right):
        await _device(client, api, ci_id, model_id=model_id)
    a_port = (await _ports(client, api, left))[4]
    b_port = (await _ports(client, api, right))[4]
    await client.post(
        f"{api}/network/connections",
        json={
            "a_interface_id": a_port["id"],
            "b_interface_id": b_port["id"],
            "medium": "FIBER",
        },
    )

    report = (await client.get(f"{api}/network/reports/free-ports")).json()
    by_name = {row["name"]: row for row in report}
    assert by_name["Коммутатор A"]["total"] == 6
    assert by_name["Коммутатор A"]["free"] == 5


async def test_redundancy_group_on_one_route_is_reported(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    left = await _ci(client, api, "Коммутатор A", "SW-A")
    right = await _ci(client, api, "Коммутатор B", "SW-B")
    for ci_id in (left, right):
        await _device(client, api, ci_id, model_id=model_id)
    left_ports = await _ports(client, api, left)
    right_ports = await _ports(client, api, right)

    route = await client.post(f"{api}/network/routes", json={"name": "Лоток A2"})
    assert route.status_code == 201, route.text
    route_id = route.json()["id"]

    for index in (4, 5):
        response = await client.post(
            f"{api}/network/connections",
            json={
                "a_interface_id": left_ports[index]["id"],
                "b_interface_id": right_ports[index]["id"],
                "medium": "FIBER",
                "is_redundant": True,
                "redundancy_group": "LAG-CORE",
                "route_id": route_id,
            },
        )
        assert response.status_code == 201, response.text

    report = (await client.get(f"{api}/network/reports/redundancy")).json()
    assert len(report) == 1
    assert any("одной трассе" in issue for issue in report[0]["issues"])


async def test_ip_address_binds_to_prefix_and_counts_capacity(
    client: AsyncClient, api: str
) -> None:
    vlan = await client.post(f"{api}/ipam/vlans", json={"vid": 20, "name": "SERVERS"})
    assert vlan.status_code == 201, vlan.text
    prefix = await client.post(
        f"{api}/ipam/prefixes",
        json={"cidr": "10.20.5.0/24", "vlan_id": vlan.json()["id"], "gateway": "10.20.5.1"},
    )
    assert prefix.status_code == 201, prefix.text
    prefix_id = prefix.json()["id"]

    model_id = await _model(client, api, await _manufacturer(client, api))
    ci_id = await _ci(client, api, "Сервер 1С", "SRV-1C-01")
    await _device(client, api, ci_id, model_id=model_id, device_role="SERVER")
    port = (await _ports(client, api, ci_id))[0]

    created = await client.post(
        f"{api}/ipam/addresses",
        json={"address": "10.20.5.17", "interface_id": port["id"], "dns_name": "srv-1c-01"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["prefix_id"] == prefix_id

    detail = (await client.get(f"{api}/ipam/prefixes/{prefix_id}")).json()
    assert detail["capacity"]["usable_total"] == 254
    assert detail["capacity"]["used"] == 1
    assert detail["next_free"][0] == "10.20.5.2"
    assert detail["addresses"][0]["ci_name"] == "Сервер 1С"

    duplicate = await client.post(f"{api}/ipam/addresses", json={"address": "10.20.5.17"})
    assert duplicate.status_code == 409


async def test_gateway_outside_prefix_is_rejected(client: AsyncClient, api: str) -> None:
    response = await client.post(
        f"{api}/ipam/prefixes", json={"cidr": "10.20.5.0/24", "gateway": "10.20.6.1"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["code_hint"] == "ip_outside_prefix"


async def test_search_finds_device_by_ip_and_mac(client: AsyncClient, api: str) -> None:
    model_id = await _model(client, api, await _manufacturer(client, api))
    ci_id = await _ci(client, api, "Сервер бухгалтерии", "SRV-BUH-01")
    await _device(
        client,
        api,
        ci_id,
        model_id=model_id,
        device_role="SERVER",
        hostname="srv-buh-01",
        mgmt_ip="10.20.9.11",
        mgmt_mac="E4-5F-01-AA-BB-CC",
    )
    port = (await _ports(client, api, ci_id))[0]
    await client.patch(f"{api}/interfaces/{port['id']}", json={"mac": "00:1a:2b:3c:4d:5e"})
    await client.post(
        f"{api}/ipam/addresses", json={"address": "10.20.5.31", "interface_id": port["id"]}
    )

    for query in ("srv-buh-01", "10.20.5.31", "e45f01aabbcc"):
        found = (await client.get(f"{api}/search", params={"q": query})).json()
        assert any(hit["entity_id"] == ci_id for hit in found["hits"]), query


async def test_device_profile_requires_device_ci_type(client: AsyncClient, api: str) -> None:
    response = await client.post(f"{api}/ci", json={"ci_type": "SERVICE", "name": "Почта"})
    ci_id = response.json()["id"]
    result = await client.put(f"{api}/devices/{ci_id}", json={"device_role": "SERVER"})
    assert result.status_code == 422
    assert result.json()["error"]["details"]["code_hint"] == "not_a_device"


async def test_device_model_change_requires_provenance(client: AsyncClient, api: str) -> None:
    manufacturer_id = await _manufacturer(client, api)
    first = await _model(client, api, manufacturer_id, model="A", templates=[])
    second = await _model(client, api, manufacturer_id, model="B", templates=[])
    ci_id = await _ci(client, api, "Коммутатор", "SW-01")
    await _device(client, api, ci_id, model_id=first)

    without_reason = await client.put(
        f"{api}/devices/{ci_id}", json={"device_role": "L3_SWITCH", "device_model_id": second}
    )
    assert without_reason.status_code == 422
    assert without_reason.json()["error"]["code"] == "provenance_required"

    reason = quote("Замена оборудования")
    with_reason = await client.put(
        f"{api}/devices/{ci_id}",
        json={"device_role": "L3_SWITCH", "device_model_id": second},
        headers={"X-Reason": reason},
    )
    assert with_reason.status_code == 200, with_reason.text
