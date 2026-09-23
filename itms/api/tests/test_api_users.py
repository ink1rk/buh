"""Учётные записи: роль с причиной, блокировка вместо удаления."""

from __future__ import annotations

from urllib.parse import quote

from httpx import AsyncClient


async def test_user_role_change_requires_reason_and_disable_keeps_account(
    client: AsyncClient, anon_client: AsyncClient, api: str
) -> None:
    weak = await client.post(
        f"{api}/users",
        json={
            "email": "weak@itms.local",
            "display_name": "Слабый пароль",
            "password": "short",
            "role": "VIEWER",
        },
    )
    assert weak.status_code == 422, weak.text

    created = await client.post(
        f"{api}/users",
        json={
            "email": "viewer@itms.local",
            "display_name": "Наблюдатель",
            "password": "Viewer-pass-1",
            "role": "VIEWER",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["status"] == "ACTIVE"
    assert "password" not in created.json()

    silent = await client.patch(f"{api}/users/{user_id}", json={"role": "ENGINEER"})
    assert silent.status_code == 422
    assert silent.json()["error"]["code"] == "provenance_required"

    changed = await client.patch(
        f"{api}/users/{user_id}",
        json={"role": "ENGINEER"},
        headers={"X-Reason": quote("допуск к каталогу")},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "ENGINEER"

    blocked = await client.patch(
        f"{api}/users/{user_id}",
        json={"status": "DISABLED"},
        headers={"X-Reason": quote("отзыв доступа")},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["status"] == "DISABLED"

    listed = await client.get(f"{api}/users")
    assert any(item["id"] == user_id for item in listed.json())

    login = await anon_client.post(
        f"{api}/auth/login",
        json={"email": "viewer@itms.local", "password": "Viewer-pass-1"},
    )
    assert login.status_code == 401
    assert login.json()["error"]["details"]["code_hint"] == "account_disabled"

    owner = next(item for item in listed.json() if item["role"] == "OWNER")
    self_off = await client.patch(
        f"{api}/users/{owner['id']}",
        json={"status": "DISABLED"},
        headers={"X-Reason": quote("проверка")},
    )
    assert self_off.status_code == 422
    assert self_off.json()["error"]["details"]["code_hint"] == "self_disable"
    demote = await client.patch(
        f"{api}/users/{owner['id']}",
        json={"role": "VIEWER"},
        headers={"X-Reason": quote("проверка")},
    )
    assert demote.status_code == 409
    assert demote.json()["error"]["details"]["code_hint"] == "last_owner"


async def test_engineer_cannot_grant_owner(
    client: AsyncClient, anon_client: AsyncClient, api: str
) -> None:
    created = await client.post(
        f"{api}/users",
        json={
            "email": "eng@itms.local",
            "display_name": "Инженер",
            "password": "Engineer-pass-1",
            "role": "ENGINEER",
        },
    )
    assert created.status_code == 201, created.text
    login = await anon_client.post(
        f"{api}/auth/login",
        json={"email": "eng@itms.local", "password": "Engineer-pass-1"},
    )
    assert login.status_code == 200, login.text
    csrf = anon_client.cookies.get("itms_csrf")
    denied = await anon_client.post(
        f"{api}/users",
        json={
            "email": "second-owner@itms.local",
            "display_name": "Второй",
            "password": "Owner-pass-1",
            "role": "OWNER",
        },
        headers={"X-CSRF-Token": csrf or ""},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["details"]["code_hint"] == "owner_grant_forbidden"
