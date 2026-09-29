"""На плане стойка и щит стоят в миллиметрах и не наезжают друг на друга."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _location(
    client: AsyncClient, api: str, name: str, location_type: str, parent: str | None = None
) -> str:
    payload: dict[str, str] = {"name": name, "location_type": location_type}
    if parent:
        payload["parent_id"] = parent
    response = await client.post(f"{api}/locations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_place_rack_and_panel_without_overlap(client: AsyncClient, api: str) -> None:
    site = await _location(client, api, "Площадка плана", "SITE")
    building = await _location(client, api, "Корпус плана", "BUILDING", site)
    room = await _location(client, api, "Комната плана", "ROOM", building)
    rack = await client.post(
        f"{api}/racks",
        json={"name": "Стойка плана", "code": "RP-1", "location_id": room, "depth_mm": 1000},
    )
    assert rack.status_code == 201, rack.text
    rack_id = rack.json()["rack"]["id"]
    panel = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Щит плана",
            "code": "RP-PN",
            "node_type": "PANEL",
            "location_id": room,
            "phases": 3,
        },
    )
    assert panel.status_code == 201, panel.text
    panel_id = panel.json()["id"]

    created = await client.post(
        f"{api}/floorplans",
        json={"name": "План комнаты", "location_id": room, "width_mm": 5000, "height_mm": 4000},
    )
    assert created.status_code == 201, created.text
    plan_id = created.json()["plan"]["id"]

    placed = await client.post(
        f"{api}/floorplans/{plan_id}/items",
        json={"ci_id": rack_id, "x": 200, "y": 200},
    )
    assert placed.status_code == 201, placed.text
    body = placed.json()
    item = body["items"][0]
    assert item["code"] == "RP-1"
    assert item["width"] == 600
    assert item["height"] == 1000
    assert body["plan"]["location_name"] == "Комната плана"

    clash = await client.post(
        f"{api}/floorplans/{plan_id}/items",
        json={"ci_id": panel_id, "x": 400, "y": 400},
    )
    assert clash.status_code == 422
    assert clash.json()["error"]["details"]["code_hint"] == "floorplan_overlap"

    clear = await client.post(
        f"{api}/floorplans/{plan_id}/items",
        json={"ci_id": panel_id, "x": 2000, "y": 200},
    )
    assert clear.status_code == 201, clear.text
    panel_item = next(row for row in clear.json()["items"] if row["code"] == "RP-PN")
    assert panel_item["item_kind"] == "POWER"

    outside = await client.patch(
        f"{api}/floorplans/{plan_id}/items/{item['id']}",
        json={"x": 4600, "y": 200},
    )
    assert outside.status_code == 422
    assert outside.json()["error"]["details"]["code_hint"] == "floorplan_outside"

    turned = await client.patch(
        f"{api}/floorplans/{plan_id}/items/{panel_item['id']}",
        json={"rotation": 90},
    )
    assert turned.status_code == 200, turned.text
    assert next(row for row in turned.json()["items"] if row["code"] == "RP-PN")["rotation"] == 90
