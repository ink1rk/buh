"""Схема показывает кабели модели и не затирает чужую раскладку."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from itms.domain.diagram import flow_layout, layered_layout

pytestmark = pytest.mark.anyio


def test_layered_layout_keeps_core_above_servers() -> None:
    positions = layered_layout(
        [
            ("srv", "DEVICE", "SERVER"),
            ("sw", "DEVICE", "L2_SWITCH"),
            ("panel", "DEVICE", "PATCH_PANEL"),
        ]
    )
    assert positions["sw"][1] < positions["panel"][1] < positions["srv"][1]


def test_flow_layout_puts_the_source_above_the_load() -> None:
    positions = flow_layout(["inlet", "panel", "load"], [("inlet", "panel"), ("panel", "load")])
    assert positions["inlet"][1] < positions["panel"][1] < positions["load"][1]


async def _location(
    client: AsyncClient, api: str, name: str, location_type: str, parent: str | None = None
) -> str:
    payload: dict[str, str] = {"name": name, "location_type": location_type}
    if parent:
        payload["parent_id"] = parent
    response = await client.post(f"{api}/locations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_diagram_follows_cables_and_layout_version(client: AsyncClient, api: str) -> None:
    site = await _location(client, api, "Офис", "SITE")
    building = await _location(client, api, "Здание", "BUILDING", site)
    room = await _location(client, api, "Серверная", "ROOM", building)

    async def device(name: str, code: str, role: str) -> tuple[str, str]:
        created = await client.post(
            f"{api}/ci",
            json={"ci_type": "DEVICE", "name": name, "code": code, "location_id": room},
        )
        assert created.status_code == 201, created.text
        ci_id = created.json()["id"]
        profile = await client.put(f"{api}/devices/{ci_id}", json={"device_role": role})
        assert profile.status_code == 200, profile.text
        port = await client.post(
            f"{api}/devices/{ci_id}/interfaces",
            json={"name": "eth1", "interface_type": "RJ45", "speed_mbps": 1000},
        )
        assert port.status_code == 201, port.text
        interface_id = port.json()[0]["id"]
        return ci_id, interface_id

    switch_id, switch_port = await device("Коммутатор", "SW-1", "L2_SWITCH")
    server_id, server_port = await device("Сервер", "SRV-1", "SERVER")
    cable = await client.post(
        f"{api}/network/connections",
        json={
            "a_interface_id": switch_port,
            "b_interface_id": server_port,
            "medium": "COPPER",
            "label": "SW-SRV",
        },
    )
    assert cable.status_code == 201, cable.text

    created = await client.post(
        f"{api}/diagrams",
        json={
            "name": "Серверная",
            "diagram_type": "NETWORK",
            "location_id": room,
            "autofill": True,
        },
    )
    assert created.status_code == 201, created.text
    diagram_id = created.json()["id"]

    full = await client.get(f"{api}/diagrams/{diagram_id}")
    assert full.status_code == 200, full.text
    body = full.json()
    labels = {node["label"] for node in body["nodes"]}
    assert labels == {"Коммутатор", "Сервер"}
    assert body["edges"][0]["label"] == "SW-SRV"
    assert body["edges"][0]["medium"] == "COPPER"
    switch = next(node for node in body["nodes"] if node["ci_id"] == switch_id)
    server = next(node for node in body["nodes"] if node["ci_id"] == server_id)
    assert switch["y"] < server["y"]

    version = body["diagram"]["version"]
    saved = await client.patch(
        f"{api}/diagrams/{diagram_id}/layout",
        json={"version": version, "nodes": [{"id": server["id"], "x": 40, "y": 500}]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == version + 1

    stale = await client.patch(
        f"{api}/diagrams/{diagram_id}/layout",
        json={"version": version, "nodes": [{"id": server["id"], "x": 1, "y": 1}]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["code_hint"] == "version_conflict"

    removed = await client.delete(f"{api}/diagrams/nodes/{server['id']}")
    assert removed.status_code == 200, removed.text
    after = (await client.get(f"{api}/diagrams/{diagram_id}")).json()
    assert [node["ci_id"] for node in after["nodes"]] == [switch_id]
    assert after["edges"] == []


async def test_power_diagram_follows_power_links(client: AsyncClient, api: str) -> None:
    site = await _location(client, api, "Площадка", "SITE")
    building = await _location(client, api, "Корпус", "BUILDING", site)
    room = await _location(client, api, "Щитовая", "ROOM", building)
    inlet = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Ввод",
            "code": "D-IN",
            "node_type": "INPUT",
            "location_id": room,
            "phases": 3,
            "max_load_w": 10000,
        },
    )
    assert inlet.status_code == 201, inlet.text
    load = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Нагрузка",
            "code": "D-LD",
            "node_type": "GENERIC_LOAD",
            "location_id": room,
            "phases": 3,
            "phase_label": "L1L2L3",
            "power_nameplate_w": 1000,
            "utilization": 1,
        },
    )
    assert load.status_code == 201, load.text
    linked = await client.post(
        f"{api}/power/links",
        json={"source_node_id": inlet.json()["id"], "target_node_id": load.json()["id"]},
    )
    assert linked.status_code == 201, linked.text

    created = await client.post(
        f"{api}/diagrams",
        json={
            "name": "Питание щитовой",
            "diagram_type": "POWER",
            "location_id": room,
            "autofill": True,
        },
    )
    assert created.status_code == 201, created.text
    full = await client.get(f"{api}/diagrams/{created.json()['id']}")
    assert full.status_code == 200, full.text
    body = full.json()
    assert {node["code"] for node in body["nodes"]} == {"D-IN", "D-LD"}
    source = next(node for node in body["nodes"] if node["code"] == "D-IN")
    target = next(node for node in body["nodes"] if node["code"] == "D-LD")
    assert source["y"] < target["y"]
    assert source["power_node_type"] == "INPUT"
    assert source["inlet_w"] == 1000
    assert body["edges"][0]["power_link_id"] == linked.json()["id"]
    assert body["edges"][0]["connection_id"] is None
