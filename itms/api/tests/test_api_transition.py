"""План поднимает предел ввода и возвращает прежние значения."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

_ITEMS = [
    {
        "name": "Сервер",
        "nameplate_w": 1200,
        "quantity": 2,
        "utilization": 0.7,
        "behind_new_ups": True,
    },
    {
        "name": "СХД",
        "nameplate_w": 1600,
        "quantity": 1,
        "utilization": 0.75,
        "behind_new_ups": True,
    },
    {
        "name": "Коммутатор",
        "nameplate_w": 350,
        "quantity": 2,
        "utilization": 0.85,
        "behind_new_ups": True,
    },
]


async def test_snapshot_plan_apply_and_rollback(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/projects",
        json={"key": "upg", "name": "Увеличение ввода", "description": "Тест перехода"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["project"]["id"]

    inlet = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Ввод теста",
            "code": "UPG-IN",
            "node_type": "INPUT",
            "phases": 3,
            "voltage_v": 400,
            "rated_current_a": 32,
            "power_factor": 0.95,
            "max_load_w": 20000,
        },
    )
    assert inlet.status_code == 201, inlet.text
    load = await client.post(
        f"{api}/power/nodes",
        json={
            "name": "Нагрузка теста",
            "code": "UPG-LD",
            "node_type": "GENERIC_LOAD",
            "phases": 3,
            "phase_label": "L1L2L3",
            "power_nameplate_w": 24000,
            "utilization": 0.7,
        },
    )
    assert load.status_code == 201, load.text
    linked = await client.post(
        f"{api}/power/links",
        json={"source_node_id": inlet.json()["id"], "target_node_id": load.json()["id"]},
    )
    assert linked.status_code == 201, linked.text
    scenario = await client.post(
        f"{api}/power/scenarios",
        json={
            "name": "Цель",
            "project_id": project_id,
            "charge_w": 900,
            "ups_efficiency": 0.94,
            "reserve": 0.2,
            "items": _ITEMS,
        },
    )
    assert scenario.status_code == 201, scenario.text

    snapshot = await client.post(
        f"{api}/projects/{project_id}/snapshots",
        json={"name": "До"},
    )
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["deficit_w"] == 497

    plan = await client.post(f"{api}/projects/{project_id}/plans")
    assert plan.status_code == 201, plan.text
    body = plan.json()
    item = body["plans"][0]["items"][0]
    assert item["payload"]["fields"]["max_load_w"] == 32909
    assert item["payload"]["fields"]["rated_current_a"] == 50
    refs = [row["payload"].get("ref") for row in body["plans"][0]["items"]]
    assert refs[1:] == [
        "R2",
        "UPS-2",
        "PDU-R2-A",
        "PDU-R2-B",
        "link-ups",
        "link-pdu-a",
        "link-pdu-b",
    ]
    levels = {row["rule"]: row["level"] for row in body["gap"]}
    assert levels["power_target"] == "OK"
    assert levels["power_unapplied"] == "WARNING"
    plan_id = body["plans"][0]["id"]

    planning = await client.get(f"{api}/projects/{project_id}")
    assert planning.status_code == 200
    assert all(row["rule"] != "power_deficit" for row in planning.json()["health"]["findings"])

    started = await client.patch(
        f"{api}/projects/{project_id}",
        json={"status": "IN_PROGRESS"},
    )
    assert started.status_code == 200, started.text
    assert any(row["rule"] == "power_deficit" for row in started.json()["health"]["findings"])
    assert started.json()["health"]["status"] == "AT_RISK"

    silent = await client.post(f"{api}/projects/{project_id}/plans/{plan_id}/apply")
    assert silent.status_code == 422
    assert silent.json()["error"]["code"] == "provenance_required"

    applied = await client.post(
        f"{api}/projects/{project_id}/plans/{plan_id}/apply",
        headers={"X-Project-Id": project_id},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["plans"][0]["status"] == "APPLIED"
    assert all(row["rule"] != "power_unapplied" for row in applied.json()["gap"])

    overview = await client.get(f"{api}/power")
    assert overview.status_code == 200
    node = next(row for row in overview.json()["nodes"] if row["code"] == "UPG-IN")
    assert node["limit_w"] == 32909
    codes = {row["code"] for row in overview.json()["nodes"]}
    assert {"UPS-2", "PDU-R2-A", "PDU-R2-B"} <= codes
    racks = await client.get(f"{api}/racks")
    assert racks.status_code == 200
    assert any(row["code"] == "R2" for row in racks.json())
    forecast = overview.json()["scenarios"][0]["forecast"]
    assert forecast["target_estimated_w"] == 20497
    assert forecast["deficit_w"] == 0

    healthy = await client.get(f"{api}/projects/{project_id}")
    assert healthy.json()["health"]["status"] == "ON_TRACK"

    rolled = await client.post(
        f"{api}/projects/{project_id}/plans/{plan_id}/rollback",
        headers={"X-Project-Id": project_id},
    )
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["live"]["limit_w"] == 20000
    assert rolled.json()["live"]["deficit_w"] == 497
    assert rolled.json()["plans"][0]["status"] == "DRAFT"
    cleared = await client.get(f"{api}/power")
    left = {row["code"] for row in cleared.json()["nodes"]}
    assert "UPS-2" not in left
    assert "R2" not in {row["code"] for row in (await client.get(f"{api}/racks")).json()}

    again = await client.get(f"{api}/projects/{project_id}")
    assert again.json()["health"]["status"] == "AT_RISK"
