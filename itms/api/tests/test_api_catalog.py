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
    assert sum(item["count"] for item in model["port_templates"]) == 5

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
