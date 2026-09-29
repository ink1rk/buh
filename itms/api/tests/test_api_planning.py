"""Шаблон собирает проект, повтор порождает новый экземпляр, сводка считает факты."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_template_recurrence_view_and_analytics(client: AsyncClient, api: str) -> None:
    created = await client.post(
        f"{api}/projects/from-template",
        json={"template": "infrastructure", "key": "inf", "name": "Площадка"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    project_id = body["project"]["id"]
    assert [phase["name"] for phase in body["phases"]] == [
        "Обследование",
        "Проектирование",
        "Внедрение",
        "Проверка",
    ]
    assert len(body["tasks"]) == 5
    assert body["milestones"][0]["name"] == "Запуск"

    repeated = await client.post(
        f"{api}/projects/{project_id}/recurrences",
        json={"title": "Проверить резервные копии", "cadence": "weekly", "weekday": 0},
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()[0]["cadence"] == "weekly"
    listed = await client.get(f"{api}/projects/{project_id}")
    backup = next(
        task for task in listed.json()["tasks"] if task["title"] == "Проверить резервные копии"
    )
    commented = await client.post(
        f"{api}/projects/{project_id}/tasks/{backup['id']}/comments",
        json={"body": "Старый комментарий"},
    )
    assert commented.status_code == 201
    done = await client.patch(
        f"{api}/projects/{project_id}/tasks/{backup['id']}",
        json={"status": "IN_PROGRESS"},
    )
    assert done.status_code == 200, done.text
    done = await client.patch(
        f"{api}/projects/{project_id}/tasks/{backup['id']}",
        json={"status": "DONE"},
    )
    assert done.status_code == 200, done.text
    titles = [
        task["title"]
        for task in done.json()["tasks"]
        if task["title"] == "Проверить резервные копии"
    ]
    assert len(titles) == 2
    fresh = next(
        task
        for task in done.json()["tasks"]
        if task["title"] == "Проверить резервные копии" and task["status"] == "NEW"
    )
    work = await client.get(f"{api}/projects/{project_id}/tasks/{fresh['id']}/work")
    assert work.json()["comments"] == []

    saved = await client.post(
        f"{api}/projects/views",
        json={"name": "Просрочено", "bucket": "overdue"},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()[0]["bucket"] == "overdue"

    report = await client.get(f"{api}/projects/analytics")
    assert report.status_code == 200, report.text
    assert report.json()["completed"] >= 1
    assert report.json()["open"] >= 1
