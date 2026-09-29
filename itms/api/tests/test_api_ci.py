from __future__ import annotations

from urllib.parse import quote

from httpx import AsyncClient


async def _create_location(client: AsyncClient, api: str) -> str:
    site = await client.post(
        f"{api}/locations", json={"name": "Офис", "location_type": "SITE"}
    )
    assert site.status_code == 201, site.text
    building = await client.post(
        f"{api}/locations",
        json={"name": "Здание А", "location_type": "BUILDING", "parent_id": site.json()["id"]},
    )
    floor = await client.post(
        f"{api}/locations",
        json={"name": "1 этаж", "location_type": "FLOOR", "parent_id": building.json()["id"]},
    )
    room = await client.post(
        f"{api}/locations",
        json={"name": "Серверная", "location_type": "ROOM", "parent_id": floor.json()["id"]},
    )
    assert room.status_code == 201, room.text
    assert room.json()["path"] == "Офис / Здание А / 1 этаж / Серверная"
    return room.json()["id"]


async def test_create_and_read_ci(client: AsyncClient, api: str) -> None:
    room_id = await _create_location(client, api)
    response = await client.post(
        f"{api}/ci",
        json={
            "ci_type": "DEVICE",
            "code": "SRV-01",
            "name": "Сервер 1",
            "location_id": room_id,
            "serial_number": "SN-777",
            "tags": ["прод", "виртуализация"],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["code"] == "SRV-01"
    assert sorted(payload["tags"]) == ["виртуализация", "прод"]

    listing = await client.get(f"{api}/ci", params={"q": "серв"})
    assert listing.json()["total"] == 1

    by_location = await client.get(f"{api}/ci", params={"location_id": room_id})
    assert by_location.json()["total"] == 1


async def test_duplicate_code_rejected(client: AsyncClient, api: str) -> None:
    await client.post(f"{api}/ci", json={"ci_type": "DEVICE", "code": "SW-1", "name": "Свитч"})
    duplicate = await client.post(
        f"{api}/ci", json={"ci_type": "DEVICE", "code": "SW-1", "name": "Другой свитч"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


async def test_invalid_status_transition_rejected(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/ci", json={"ci_type": "OTHER", "name": "Тестовый объект", "criticality": "LOW"}
    )
    ci_id = created.json()["id"]
    await client.patch(
        f"{api}/ci/{ci_id}",
        json={"status": "DECOMMISSIONING"},
        headers={"X-Reason": quote("вывод из эксплуатации")},
    )
    await client.patch(
        f"{api}/ci/{ci_id}", json={"status": "RETIRED"}, headers={"X-Reason": quote("списан")}
    )
    invalid = await client.patch(
        f"{api}/ci/{ci_id}", json={"status": "ACTIVE"}, headers={"X-Reason": quote("вернуть")}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["code_hint"] == "invalid_status_transition"


async def test_optimistic_locking(client: AsyncClient, api: str) -> None:
    created = await client.post(f"{api}/ci", json={"ci_type": "OTHER", "name": "Объект"})
    ci_id = created.json()["id"]
    stale_version = created.json()["version"]
    await client.patch(f"{api}/ci/{ci_id}", json={"name": "Объект (обновлён)"})
    conflict = await client.patch(
        f"{api}/ci/{ci_id}", json={"name": "Ещё раз", "version": stale_version}
    )
    assert conflict.status_code == 409


async def test_relations_and_related_panel(client: AsyncClient, api: str) -> None:
    service = await client.post(f"{api}/ci", json={"ci_type": "SERVICE", "name": "1С"})
    server = await client.post(f"{api}/ci", json={"ci_type": "DEVICE", "name": "Сервер 1С"})
    relation = await client.post(
        f"{api}/relations",
        json={
            "source_ci_id": service.json()["id"],
            "target_ci_id": server.json()["id"],
            "rel_type": "DEPENDS_ON",
        },
    )
    assert relation.status_code == 201, relation.text

    related = await client.get(f"{api}/ci/{server.json()['id']}/related")
    assert related.status_code == 200
    incoming = related.json()["depends_on"]
    assert incoming[0]["direction"] == "incoming"
    assert incoming[0]["ci"]["name"] == "1С"

    cycle = await client.post(
        f"{api}/relations",
        json={
            "source_ci_id": server.json()["id"],
            "target_ci_id": service.json()["id"],
            "rel_type": "DEPENDS_ON",
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "cycle_detected"


async def test_power_relation_rejected_by_api(client: AsyncClient, api: str) -> None:
    ups = await client.post(f"{api}/ci", json={"ci_type": "POWER_NODE", "name": "ИБП-1"})
    pdu = await client.post(f"{api}/ci", json={"ci_type": "POWER_NODE", "name": "PDU-A"})
    response = await client.post(
        f"{api}/relations",
        json={
            "source_ci_id": pdu.json()["id"],
            "target_ci_id": ups.json()["id"],
            "rel_type": "DEPENDS_ON",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["code_hint"] == "power_relation_forbidden"


async def test_critical_object_cannot_be_deleted(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/ci",
        json={"ci_type": "APPLICATION", "name": "Биллинг", "criticality": "CRITICAL"},
    )
    response = await client.delete(f"{api}/ci/{created.json()['id']}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "deletion_forbidden"

    archived = await client.post(f"{api}/ci/{created.json()['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    listing = await client.get(f"{api}/ci")
    assert listing.json()["total"] == 0
    archived_listing = await client.get(f"{api}/ci", params={"archived": True})
    assert archived_listing.json()["total"] == 1


async def test_ci_list_filters_criticality_and_missing_owner(client: AsyncClient, api: str) -> None:
    critical = await client.post(
        f"{api}/ci", json={"ci_type": "DEVICE", "name": "Критичный", "criticality": "CRITICAL"}
    )
    await client.post(
        f"{api}/ci", json={"ci_type": "OTHER", "name": "Обычный", "criticality": "LOW"}
    )
    by_criticality = await client.get(f"{api}/ci", params={"criticality": "CRITICAL"})
    assert by_criticality.status_code == 200
    assert [item["id"] for item in by_criticality.json()["items"]] == [critical.json()["id"]]
    missing = await client.get(f"{api}/ci", params={"without_owner": True})
    assert missing.json()["total"] >= 2


async def test_ordinary_object_can_be_soft_deleted(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/ci", json={"ci_type": "OTHER", "name": "Черновик", "criticality": "LOW"}
    )
    response = await client.delete(f"{api}/ci/{created.json()['id']}")
    assert response.status_code == 200
    assert (await client.get(f"{api}/ci")).json()["total"] == 0
