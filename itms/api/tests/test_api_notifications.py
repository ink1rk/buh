"""Назначение, статус и упоминание доходят до учётной записи исполнителя, автору — нет."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from itms.core.config import settings
from itms.core.db import session_scope
from itms.core.security import hash_password
from itms.main import app
from itms.models.directory import UserAccount
from itms.models.enums import UserRole, UserStatus

pytestmark = pytest.mark.anyio


async def _login(email: str, password: str) -> AsyncClient:
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    client.headers[settings.csrf_header] = client.cookies.get(settings.csrf_cookie) or ""
    return client


async def test_assignee_hears_about_task_and_author_does_not(client: AsyncClient, api: str) -> None:
    employee = await client.post(
        f"{api}/directory/employees",
        json={"full_name": "Инженер Смены", "position": "Инженер", "support_line": "SECOND"},
    )
    assert employee.status_code == 201, employee.text
    async with session_scope() as db:
        db.add(
            UserAccount(
                email="eng@itms.local",
                display_name="Инженер",
                password_hash=hash_password("engineer-password-1"),
                role=UserRole.VIEWER,
                status=UserStatus.ACTIVE,
                employee_id=employee.json()["id"],
            )
        )

    created = await client.post(f"{api}/projects", json={"key": "ntf", "name": "Сигналы"})
    assert created.status_code == 201, created.text
    project_id = created.json()["project"]["id"]
    task = await client.post(
        f"{api}/projects/{project_id}/tasks",
        json={"title": "Проверить ввод", "assignee_id": employee.json()["id"]},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["tasks"][0]["id"]

    viewer = await _login("eng@itms.local", "engineer-password-1")
    try:
        first = await viewer.get(f"{api}/notifications")
        assert first.status_code == 200, first.text
        assert first.json()["unread"] == 1
        assert first.json()["items"][0]["kind"] == "assigned"
        assert first.json()["items"][0]["title"].startswith("NTF-1")

        commented = await client.post(
            f"{api}/projects/{project_id}/tasks/{task_id}/comments",
            json={"body": "@Инженер сверь фазы"},
        )
        assert commented.status_code == 201, commented.text
        moved = await client.patch(
            f"{api}/projects/{project_id}/tasks/{task_id}",
            json={"status": "IN_PROGRESS"},
        )
        assert moved.status_code == 200, moved.text

        listed = await viewer.get(f"{api}/notifications")
        kinds = [item["kind"] for item in listed.json()["items"]]
        assert kinds == ["status", "mention", "assigned"]
        assert listed.json()["unread"] == 3

        own = await client.get(f"{api}/notifications")
        assert own.json()["unread"] == 0

        foreign = listed.json()["items"][0]["id"]
        hidden = await client.post(f"{api}/notifications/{foreign}/read")
        assert hidden.status_code == 404

        read = await viewer.post(f"{api}/notifications/{foreign}/read")
        assert read.status_code == 200, read.text
        assert read.json()["unread"] == 2
        cleared = await viewer.post(f"{api}/notifications/read")
        assert cleared.json()["unread"] == 0
    finally:
        await viewer.aclose()
