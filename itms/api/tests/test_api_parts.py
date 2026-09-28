"""Комплектация сервера ограничена сокетами, слотами и корзинами модели."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def _model(
    client: AsyncClient,
    api: str,
    manufacturer_id: str,
    model: str,
    **extra: Any,
) -> str:
    payload = {
        "manufacturer_id": manufacturer_id,
        "model": model,
        "default_role": extra.pop("default_role", "SERVER"),
        "u_height": extra.pop("u_height", 2),
        "component_class": extra.pop("component_class", "CHASSIS"),
        **extra,
    }
    response = await client.post(f"{api}/catalog/models", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_parts_follow_platform_limits(client: AsyncClient, api: str) -> None:
    vendor = await client.post(f"{api}/catalog/manufacturers", json={"name": "HPE"})
    assert vendor.status_code == 201, vendor.text
    manufacturer_id = vendor.json()["id"]
    server = await _model(
        client,
        api,
        manufacturer_id,
        "DL380-test",
        cpu_sockets=2,
        cpu_socket="LGA4677",
        ram_slots=4,
        ram_type="DDR5",
        drive_bays=2,
        drive_form="SFF",
        psu_count=2,
    )
    cpu = await _model(
        client,
        api,
        manufacturer_id,
        "Xeon Gold 6430",
        default_role="OTHER",
        u_height=0,
        component_class="CPU",
        cpu_socket="LGA4677",
    )
    wrong = await _model(
        client,
        api,
        manufacturer_id,
        "EPYC 9354",
        default_role="OTHER",
        u_height=0,
        component_class="CPU",
        cpu_socket="SP5",
    )
    memory = await _model(
        client,
        api,
        manufacturer_id,
        "DDR5 64 ГБ",
        default_role="OTHER",
        u_height=0,
        component_class="MEMORY",
        ram_type="DDR5",
    )
    ci = await client.post(f"{api}/ci", json={"ci_type": "DEVICE", "name": "srv", "code": "srv-1"})
    assert ci.status_code == 201, ci.text
    ci_id = ci.json()["id"]
    profile = await client.put(
        f"{api}/devices/{ci_id}",
        json={"device_role": "SERVER", "device_model_id": server, "psu_count": 2},
    )
    assert profile.status_code == 200, profile.text

    fitted = await client.put(
        f"{api}/devices/{ci_id}/parts",
        json={"component_model_id": cpu, "quantity": 2},
    )
    assert fitted.status_code == 200, fitted.text
    assert fitted.json()["cpu_sockets"] == 2
    assert len(fitted.json()["items"]) == 1

    overflow = await client.put(
        f"{api}/devices/{ci_id}/parts",
        json={"component_model_id": cpu, "quantity": 3},
    )
    assert overflow.status_code == 422, overflow.text

    mismatch = await client.put(
        f"{api}/devices/{ci_id}/parts",
        json={"component_model_id": wrong, "quantity": 1},
    )
    assert mismatch.status_code == 422, mismatch.text

    dimms = await client.put(
        f"{api}/devices/{ci_id}/parts",
        json={"component_model_id": memory, "quantity": 4},
    )
    assert dimms.status_code == 200, dimms.text
    too_many = await client.put(
        f"{api}/devices/{ci_id}/parts",
        json={"component_model_id": memory, "quantity": 5},
    )
    assert too_many.status_code == 422, too_many.text
