"""Tests for MCP over HTTP: the door the assistant knocks on.

The protocol itself is covered by test_mcp_server.py. What matters here is the
transport and the guard on it, because this is the only write-capable endpoint
in the app that an unattended process may call.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.mcp.client import FinanceApiClient

ACCOUNTS = [
    {"id": 1, "name": "Ozon Банк", "account_type": "bank",
     "balance": 226635.94, "currency": "RUB"},
]

TOKEN = "s3cret-token"


def _finance(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/accounts"):
        return httpx.Response(200, json=ACCOUNTS)
    return httpx.Response(404, json={"detail": "not used in this test"})


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(get_settings(), "mcp_token", TOKEN)
    return TOKEN


@pytest.fixture
def stub_finance(monkeypatch):
    """Инструменты ходят в API приложения — в тесте отвечаем за него сами."""
    monkeypatch.setattr(
        "app.api.routes.mcp.FinanceApiClient",
        lambda: FinanceApiClient(transport=httpx.MockTransport(_finance)))


def _rpc(method: str, params: dict | None = None, message_id: int | None = 1):
    body: dict = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if message_id is not None:
        body["id"] = message_id
    return body


async def test_without_a_token_the_endpoint_does_not_exist(client):
    """Незакрытая точка с пишущими инструментами хуже, чем её отсутствие."""
    assert not get_settings().mcp_token

    response = await client.post("/api/v1/mcp", json=_rpc("tools/list"))

    assert response.status_code == 404


async def test_a_wrong_token_is_refused(client, token):
    response = await client.post("/api/v1/mcp", json=_rpc("tools/list"),
                                 headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401


async def test_a_missing_token_is_refused_when_one_is_required(client, token):
    response = await client.post("/api/v1/mcp", json=_rpc("tools/list"))

    assert response.status_code == 401


async def test_the_handshake_agrees_on_a_version(client, token):
    response = await client.post(
        "/api/v1/mcp",
        json=_rpc("initialize", {"protocolVersion": "2025-06-18"}),
        headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "personal-finance-ai"


async def test_the_assistant_sees_the_tools(client, token):
    response = await client.post("/api/v1/mcp", json=_rpc("tools/list"),
                                 headers={"Authorization": f"Bearer {token}"})

    names = [tool["name"] for tool in response.json()["result"]["tools"]]
    assert "get_financial_overview" in names
    assert all(tool.get("inputSchema") for tool in response.json()["result"]["tools"])


async def test_a_tool_call_answers_with_the_app_data(client, token, stub_finance):
    response = await client.post(
        "/api/v1/mcp",
        json=_rpc("tools/call", {"name": "list_accounts", "arguments": {}}),
        headers={"Authorization": f"Bearer {token}"})

    result = response.json()["result"]
    assert result["isError"] is False
    assert "Ozon Банк" in result["content"][0]["text"]


async def test_a_notification_gets_no_answer(client, token):
    """Ответ на уведомление — нарушение протокола: у него нет id."""
    response = await client.post(
        "/api/v1/mcp", json=_rpc("notifications/initialized", message_id=None),
        headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 202
    assert not response.content


async def test_broken_json_is_reported_in_protocol_terms(client, token):
    response = await client.post("/api/v1/mcp", content=b"{not json",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})

    assert response.json()["error"]["code"] == -32700


async def test_an_unknown_method_is_an_error_not_a_crash(client, token):
    response = await client.post("/api/v1/mcp", json=_rpc("tools/destroy"),
                                 headers={"Authorization": f"Bearer {token}"})

    assert response.json()["error"]["code"] == -32601


async def test_an_oversized_body_is_refused(client, token):
    response = await client.post(
        "/api/v1/mcp", content=b'{"padding":"' + b"x" * (256 * 1024) + b'"}',
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})

    assert response.status_code == 413
