"""Библиотека каталога ставится повторно без дубликатов."""

from __future__ import annotations

from httpx import AsyncClient

from itms.domain.catalog_library import LIBRARY


async def test_catalog_library_is_idempotent(client: AsyncClient, api: str) -> None:
    first = await client.post(f"{api}/catalog/library")
    assert first.status_code == 200, first.text
    created = first.json()
    assert created["models_created"] == len(LIBRARY)
    assert created["models_skipped"] == 0
    assert created["manufacturers_created"] >= 8

    listed = await client.get(f"{api}/catalog/models", params={"q": "PowerEdge R750", "limit": 10})
    assert listed.status_code == 200, listed.text
    model = listed.json()["items"][0]
    assert model["power_nameplate_w"] == 800
    assert model["u_height"] == 2
    assert model["cpu_socket"] == "LGA4189"
    assert model["ram_slots"] == 32
    assert sum(item["count"] for item in model["port_templates"]) == 5

    platform = await client.get(
        f"{api}/catalog/models", params={"q": "DL380 Gen11", "limit": 10}
    )
    dl380 = platform.json()["items"][0]
    assert dl380["cpu_sockets"] == 2
    assert dl380["cpu_socket"] == "LGA4677"
    assert dl380["u_height"] == 2

    storage = await client.get(f"{api}/catalog/models", params={"q": "3PAR 8200", "limit": 10})
    assert storage.json()["items"][0]["u_height"] == 2
    assert storage.json()["items"][0]["drive_bays"] == 24

    keys = {(item.manufacturer.lower(), item.model) for item in LIBRARY}
    assert len(keys) == len(LIBRARY)
    gen9 = next(item for item in LIBRARY if item.model == "ProLiant DL380 Gen9")
    assert gen9.manufacturer == "HP"
    assert gen9.cpu_socket == "LGA2011-3"
    hp_servers = [
        item
        for item in LIBRARY
        if item.manufacturer == "HP" and item.default_role.value == "SERVER"
    ]
    assert len(hp_servers) >= 50
    dell_servers = [
        item
        for item in LIBRARY
        if item.manufacturer == "Dell" and item.default_role.value == "SERVER"
    ]
    assert len(dell_servers) >= 60
    assert not any(item.manufacturer.lower() == "hpe" for item in LIBRARY)
    assert gen9.ram_type == "DDR4"
    assert gen9.u_height == 2
    crs = next(item for item in LIBRARY if item.model == "CRS354-48P-4S+2Q+RM")
    assert sum(port.count for port in crs.ports) == 54
    poe = next(item for item in LIBRARY if item.model == "MES2348P")
    assert sum(port.count for port in poe.ports) == 52
    assert any(port.poe_capable for port in poe.ports)

    ups = await client.get(f"{api}/catalog/models", params={"q": "Smart-UPS", "limit": 10})
    assert ups.json()["items"][0]["power_nameplate_w"] is None
    assert "ёмкость" in ups.json()["items"][0]["notes"]

    second = await client.post(f"{api}/catalog/library")
    assert second.status_code == 200, second.text
    again = second.json()
    assert again["models_created"] == 0
    assert again["manufacturers_created"] == 0
    assert again["models_skipped"] == len(LIBRARY)


async def test_catalog_library_reuses_existing_manufacturer(client: AsyncClient, api: str) -> None:
    made = await client.post(f"{api}/catalog/manufacturers", json={"name": "MikroTik"})
    assert made.status_code == 201, made.text
    response = await client.post(f"{api}/catalog/library")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["manufacturers_skipped"] >= 1
    assert body["models_created"] == len(LIBRARY)
    vendors = await client.get(f"{api}/catalog/manufacturers", params={"q": "mikro"})
    assert len(vendors.json()) == 1
