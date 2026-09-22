"""Схема показывает кабели модели и не затирает чужую раскладку."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from itms.domain.diagram import layered_layout

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
