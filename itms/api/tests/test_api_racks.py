"""Стойка не даёт поставить два устройства в одни юниты и считает свободные блоки."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from itms.domain.racks import free_blocks, occupies, spans_overlap, units_for_model

pytestmark = pytest.mark.anyio


def test_free_blocks_and_faces() -> None:
    assert free_blocks(10, [(1, 2), (8, 1)]) == [
        {"start": 3, "length": 5},
        {"start": 9, "length": 2},
    ]
    assert occupies("FULL", "REAR")
    assert not occupies("FRONT", "REAR")
    assert spans_overlap(1, 2, 2, 2)
    assert not spans_overlap(1, 2, 3, 1)
    assert units_for_model(0.5) == 1
    assert units_for_model(0) == 0


async def _device(client: AsyncClient, api: str, name: str, code: str) -> str:
    response = await client.post(
        f"{api}/ci",
        json={"ci_type": "DEVICE", "name": name, "code": code},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_rack_rejects_overlap_and_reports_free_units(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/racks",
        json={"name": "R1", "code": "R1", "u_height": 10, "max_weight_kg": 5, "depth_mm": 800},
    )
    assert created.status_code == 201, created.text
    rack_id = created.json()["rack"]["id"]
    server = await _device(client, api, "Сервер", "SRV")
    switch = await _device(client, api, "Коммутатор", "SW")

    placed = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": server, "position_u": 1, "u_height": 2, "face": "FRONT", "weight_kg": 3},
    )
    assert placed.status_code == 200, placed.text
    body = placed.json()
    assert body["free_front"][0] == {"start": 3, "length": 8}
    assert body["capacity"]["used_front"] == 2

    overlap = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": switch, "position_u": 2, "u_height": 1, "face": "FRONT"},
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["details"]["code_hint"] == "u_overlap"

    rear = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": switch, "position_u": 1, "u_height": 1, "face": "REAR"},
    )
    assert rear.status_code == 200, rear.text

    full = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": switch, "position_u": 1, "u_height": 1, "face": "FULL"},
    )
    assert full.status_code == 409

    outside = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": switch, "position_u": 10, "u_height": 2, "face": "REAR"},
    )
    assert outside.status_code == 422
    assert outside.json()["error"]["details"]["code_hint"] == "out_of_rack"

    heavy = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={
            "ci_id": switch,
            "position_u": 8,
            "u_height": 1,
            "face": "FRONT",
            "weight_kg": 4,
        },
    )
    assert heavy.status_code == 409
    assert heavy.json()["error"]["details"]["code_hint"] == "weight_exceeded"
    confirmed = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={
            "ci_id": switch,
            "position_u": 8,
            "u_height": 1,
            "face": "FRONT",
            "weight_kg": 4,
            "confirm_warnings": True,
        },
        headers={"X-Reason": "confirm weight"},
    )
    assert confirmed.status_code == 200, confirmed.text

    mount_id = next(item["id"] for item in confirmed.json()["mounts"] if item["ci_id"] == switch)
    moved = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": switch, "position_u": 5, "u_height": 1, "face": "FRONT", "weight_kg": 1},
        headers={"X-Reason": "move"},
    )
    assert moved.status_code == 200, moved.text
    assert any(item["position_u"] == 5 for item in moved.json()["mounts"])

    pdu = await _device(client, api, "PDU", "PDU-1")
    side = await client.put(
        f"{api}/racks/{rack_id}/mounts",
        json={"ci_id": pdu, "u_height": 0, "zero_u_side": "LEFT"},
    )
    assert side.status_code == 200, side.text
    assert any(item["u_height"] == 0 for item in side.json()["mounts"])

    removed = await client.delete(f"{api}/racks/{rack_id}/mounts/{mount_id}")
    assert removed.status_code == 200, removed.text
    assert all(item["ci_id"] != switch for item in removed.json()["mounts"])
    assert any(item["ci_id"] == switch for item in removed.json()["warehouse"])
