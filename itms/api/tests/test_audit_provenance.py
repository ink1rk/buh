"""Аудит и происхождение изменений — сквозное требование системы."""

from __future__ import annotations

import uuid
from urllib.parse import quote

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


async def test_history_records_field_changes(client: AsyncClient, api: str) -> None:
    created = await client.post(f"{api}/ci", json={"ci_type": "OTHER", "name": "Объект"})
    ci_id = created.json()["id"]
    await client.patch(f"{api}/ci/{ci_id}", json={"name": "Объект переименован"})

    history = (await client.get(f"{api}/ci/{ci_id}/history")).json()
    actions = [entry["action"] for entry in history]
    assert "CREATE" in actions and "UPDATE" in actions

    update_entry = next(entry for entry in history if entry["action"] == "UPDATE")
    change = next(c for c in update_entry["changes"] if c["field"] == "name")
    assert change["old_value"] == "Объект"
    assert change["new_value"] == "Объект переименован"


async def test_critical_field_requires_provenance(client: AsyncClient, api: str) -> None:
    created = await client.post(f"{api}/ci", json={"ci_type": "OTHER", "name": "Объект"})
    ci_id = created.json()["id"]

    silent = await client.patch(f"{api}/ci/{ci_id}", json={"criticality": "CRITICAL"})
    assert silent.status_code == 422
    assert silent.json()["error"]["code"] == "provenance_required"

    with_reason = await client.patch(
        f"{api}/ci/{ci_id}",
        json={"criticality": "CRITICAL"},
        headers={"X-Reason": quote("объект признан критичным после аудита")},
    )
    assert with_reason.status_code == 200


async def test_provenance_traces_change_to_project_and_task(
    client: AsyncClient, api: str
) -> None:
    created = await client.post(
        f"{api}/ci", json={"ci_type": "DEVICE", "name": "Сервер 7", "criticality": "LOW"}
    )
    ci_id = created.json()["id"]
    project_id, task_id, change_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    response = await client.patch(
        f"{api}/ci/{ci_id}",
        json={"criticality": "HIGH"},
        headers={
            "X-Project-Id": project_id,
            "X-Task-Id": task_id,
            "X-Change-Id": change_id,
            "X-Reason": quote("модернизация серверной"),
        },
    )
    assert response.status_code == 200

    provenance = await client.get(
        f"{api}/ci/{ci_id}/provenance", params={"field": "criticality"}
    )
    assert provenance.status_code == 200
    entry = provenance.json()[0]
    assert entry["old_value"] == "LOW"
    assert entry["new_value"] == "HIGH"
    assert entry["project_id"] == project_id
    assert entry["task_id"] == task_id
    assert entry["change_id"] == change_id
    assert entry["reason"] == "модернизация серверной"


async def test_audit_log_is_immutable_in_database(session: AsyncSession) -> None:
    """Неизменяемость обеспечивается базой, а не добросовестностью кода."""
    await session.execute(
        text(
            "INSERT INTO audit_log (entity_type, action, actor_kind, source) "
            "VALUES ('CI', 'UPDATE', 'SYSTEM', 'test')"
        )
    )
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE audit_log SET reason = 'подделка'"))
    await session.rollback()

    # После отката строку нужно создать заново: триггер построчный и на пустой
    # таблице просто не сработает.
    await session.execute(
        text(
            "INSERT INTO audit_log (entity_type, action, actor_kind, source) "
            "VALUES ('CI', 'UPDATE', 'SYSTEM', 'test')"
        )
    )
    with pytest.raises(DBAPIError):
        await session.execute(text("DELETE FROM audit_log"))
    await session.rollback()


async def test_audit_endpoint_filters_by_provenance(client: AsyncClient, api: str) -> None:
    created = await client.post(f"{api}/ci", json={"ci_type": "OTHER", "name": "Объект"})
    ci_id = created.json()["id"]
    change_id = str(uuid.uuid4())
    await client.patch(
        f"{api}/ci/{ci_id}",
        json={"status": "MAINTENANCE"},
        headers={"X-Change-Id": change_id, "X-Reason": quote("плановые работы")},
    )

    filtered = await client.get(f"{api}/audit", params={"change_id": change_id})
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["action"] == "STATUS"
