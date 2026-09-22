"""Карточка задачи хранит комментарий и чеклист, открытые задачи видны во входящих."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_comment_check_and_inbox(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/projects",
        json={"key": "wrk", "name": "Работы", "description": "Чеклист"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["project"]["id"]
    task = await client.post(
        f"{api}/projects/{project_id}/tasks",
        json={"title": "Проверить резервные копии"},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["tasks"][0]["id"]

    commented = await client.post(
        f"{api}/projects/{project_id}/tasks/{task_id}/comments",
        json={"body": "Снял дамп"},
    )
    assert commented.status_code == 201, commented.text
    assert commented.json()["comments"][0]["body"] == "Снял дамп"

    checked = await client.post(
        f"{api}/projects/{project_id}/tasks/{task_id}/checks",
        json={"title": "Сверить размер"},
    )
    assert checked.status_code == 201, checked.text
    item = checked.json()["checks"][0]
    assert item["done"] is False
    toggled = await client.patch(
        f"{api}/projects/{project_id}/tasks/{task_id}/checks/{item['id']}",
        json={"done": True},
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["checks"][0]["done"] is True

    inbox = await client.get(f"{api}/projects/inbox")
    assert inbox.status_code == 200, inbox.text
    row = next(entry for entry in inbox.json() if entry["id"] == task_id)
    assert row["bucket"] == "undated"
    assert row["label"] == "WRK-1"
