"""Экспорт объектов в CSV пишется в аудит и не отдаётся без права."""

from __future__ import annotations

from httpx import AsyncClient


async def test_ci_csv_export_is_audited(
    client: AsyncClient, anon_client: AsyncClient, api: str
) -> None:
    created = await client.post(
        f"{api}/ci",
        json={"ci_type": "DEVICE", "name": "Экспортный коммутатор", "code": "EXP-1"},
    )
    assert created.status_code == 201, created.text

    denied = await anon_client.get(f"{api}/exports/ci.csv")
    assert denied.status_code == 401

    exported = await client.get(f"{api}/exports/ci.csv", params={"q": "EXP-1"})
    assert exported.status_code == 200, exported.text
    assert "text/csv" in exported.headers["content-type"]
    text = exported.text
    assert "EXP-1" in text
    assert "Экспортный коммутатор" in text

    audit = await client.get(f"{api}/audit", params={"action": "EXPORT"})
    assert audit.status_code == 200, audit.text
    assert audit.json()["total"] >= 1
    assert audit.json()["items"][0]["action"] == "EXPORT"
