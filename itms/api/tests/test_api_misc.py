from __future__ import annotations

import io

from httpx import AsyncClient

from itms.core.config import settings


async def test_authentication_required(anon_client: AsyncClient, api: str) -> None:
    response = await anon_client.get(f"{api}/ci")
    assert response.status_code == 401


async def test_csrf_required_for_writes(client: AsyncClient, api: str) -> None:
    headers = {settings.csrf_header: "forged-token"}
    response = await client.post(
        f"{api}/ci", json={"ci_type": "OTHER", "name": "X"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["code_hint"] == "csrf_invalid"


async def test_login_rejects_wrong_password(anon_client: AsyncClient, api: str, owner) -> None:
    response = await anon_client.post(
        f"{api}/auth/login",
        json={"email": settings.bootstrap_owner_email, "password": "неверный"},
    )
    assert response.status_code == 401


async def test_search_finds_by_serial_and_name(client: AsyncClient, api: str) -> None:
    await client.post(
        f"{api}/ci",
        json={
            "ci_type": "DEVICE",
            "code": "SRV-42",
            "name": "Сервер приложений",
            "serial_number": "CN0ABC123",
        },
    )
    by_name = await client.get(f"{api}/search", params={"q": "сервер"})
    assert by_name.json()["hits"], by_name.text

    by_serial = await client.get(f"{api}/search", params={"q": "CN0ABC123"})
    assert by_serial.json()["hits"][0]["title"] == "Сервер приложений"

    by_code_prefix = await client.get(f"{api}/search", params={"q": "SRV-4"})
    assert by_code_prefix.json()["hits"]


async def test_documents_versioning_and_links(client: AsyncClient, api: str) -> None:
    ci = await client.post(f"{api}/ci", json={"ci_type": "DEVICE", "name": "Маршрутизатор"})
    created = await client.post(
        f"{api}/documents",
        json={
            "title": "Инструкция по настройке",
            "kind": "INSTRUCTION",
            "content": "Первая редакция",
            "links": [{"entity_type": "CI", "entity_id": ci.json()["id"]}],
        },
    )
    assert created.status_code == 201, created.text
    doc_id = created.json()["id"]
    assert created.json()["content"] == "Первая редакция"

    updated = await client.patch(
        f"{api}/documents/{doc_id}",
        json={"content": "Вторая редакция", "change_note": "уточнены шаги"},
    )
    assert updated.json()["current_version"] == 2
    assert updated.json()["content"] == "Вторая редакция"

    versions = await client.get(f"{api}/documents/{doc_id}/versions")
    assert [v["version"] for v in versions.json()] == [2, 1]

    restored = await client.post(f"{api}/documents/{doc_id}/versions/1/restore")
    assert restored.json()["content"] == "Первая редакция"
    assert restored.json()["current_version"] == 3

    linked = await client.get(f"{api}/ci/{ci.json()['id']}/documents")
    assert len(linked.json()) == 1


async def test_file_upload_and_download(client: AsyncClient, api: str) -> None:
    files = {"file": ("схема.txt", io.BytesIO(b"L1 L2 L3"), "text/plain")}
    response = await client.post(f"{api}/files", files=files)
    assert response.status_code == 201, response.text
    file_id = response.json()["id"]

    content = await client.get(f"{api}/files/{file_id}/content")
    assert content.content == b"L1 L2 L3"


async def test_executable_upload_is_rejected(client: AsyncClient, api: str) -> None:
    files = {"file": ("payload.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    response = await client.post(f"{api}/files", files=files)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["code_hint"] == "file_type_blocked"


async def test_csv_import_creates_objects(client: AsyncClient, api: str) -> None:
    csv_content = (
        "Код;Наименование;Тип;Производитель;Серийный номер\n"
        "SRV-100;Сервер бухгалтерии;DEVICE;HP;SN-100\n"
        "SW-100;Коммутатор склада;DEVICE;MikroTik;SN-101\n"
    ).encode()
    files = {"file": ("cmdb.csv", io.BytesIO(csv_content), "text/csv")}
    created = await client.post(f"{api}/imports", params={"target": "CI"}, files=files)
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["rows_total"] == 2
    assert job["mapping"]["Наименование"] == "name"

    validated = await client.post(f"{api}/imports/{job['id']}/validate")
    assert validated.json()["rows_valid"] == 2
    assert validated.json()["status"] == "VALIDATED"

    applied = await client.post(f"{api}/imports/{job['id']}/apply")
    assert applied.json()["rows_created"] == 2

    listing = await client.get(f"{api}/ci")
    assert listing.json()["total"] == 2


async def test_dashboard_and_meta(client: AsyncClient, api: str) -> None:
    await client.post(
        f"{api}/ci",
        json={"ci_type": "DEVICE", "name": "Сервер", "criticality": "CRITICAL"},
    )
    dashboard = await client.get(f"{api}/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["counters"]["ci_total"] == 1
    assert payload["counters"]["ci_critical"] == 1
    assert payload["recent_activity"]

    meta = await client.get(f"{api}/meta")
    assert "POWERED_BY" not in meta.json()["relation_types"]
    assert meta.json()["power_defaults"]["derating"] == settings.power_derating_default


async def test_employee_and_workload(client: AsyncClient, api: str) -> None:
    employee = await client.post(
        f"{api}/directory/employees",
        json={"full_name": "Петров Пётр", "position": "Инженер", "support_line": "SECOND"},
    )
    assert employee.status_code == 201, employee.text
    await client.post(
        f"{api}/ci",
        json={
            "ci_type": "DEVICE",
            "name": "Сервер учёта",
            "owner_employee_id": employee.json()["id"],
        },
    )
    workload = await client.get(f"{api}/directory/workload")
    assert workload.json()[0]["owned_ci"] == 1
