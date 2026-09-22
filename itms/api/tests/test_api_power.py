"""Цепочка питания создаётся через API, цикл отклоняется до записи."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_create_link_and_calculate(client: AsyncClient, api: str) -> None:
    inlet = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Ввод теста",
            "code": "T-IN",
            "node_type": "INPUT",
            "phases": 3,
            "max_load_w": 10000,
            "voltage_v": 400,
            "power_factor": 0.95,
        },
    )
    assert inlet.status_code == 201, inlet.text
    load = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Нагрузка теста",
            "code": "T-LD",
            "node_type": "GENERIC_LOAD",
            "phases": 1,
            "phase_label": "L1",
            "power_nameplate_w": 1000,
            "utilization": 1,
        },
    )
    assert load.status_code == 201, load.text
    linked = await client.post(
        f"{api}/power/links",
        json={
            "source_node_id": inlet.json()["id"],
            "target_node_id": load.json()["id"],
        },
    )
    assert linked.status_code == 201, linked.text

    overview = await client.get(f"{api}/power")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    primary = next(row for row in body["nodes"] if row["code"] == "T-IN")
    assert primary["inlet_w"] == 1000
    assert primary["headroom_w"] == 9000
    assert body["primary_input_id"] == primary["id"]

    cycle = await client.post(
        f"{api}/power/links",
        json={
            "source_node_id": load.json()["id"],
            "target_node_id": inlet.json()["id"],
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "cycle_detected"

    missing_phase = await client.post(
        f"{api}/power/nodes",
        json={"name": "Без фазы", "node_type": "PSU", "phases": 1},
    )
    assert missing_phase.status_code == 422
    assert missing_phase.json()["error"]["details"]["code_hint"] == "phase_label_required"
