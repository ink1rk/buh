"""Tests for the MCP server: protocol handshake, tool contract and handlers."""

from __future__ import annotations

import json
from datetime import date, timedelta

import httpx
import pytest

from app.mcp.client import FinanceApiClient, FinanceApiError
from app.mcp.server import McpStdioServer, tool_descriptors
from app.mcp.tools import TOOLS, TOOLS_BY_NAME, call_tool

TODAY = date(2026, 3, 20)

TRANSACTIONS = [
    {
        "id": 1, "amount": -450.0, "currency": "RUB", "category": "cafe",
        "description": "Surf Coffee", "merchant": "Surf Coffee", "account_id": 1,
        "transaction_type": "expense", "occurred_on": "2026-03-18", "tags": "bank,ozon",
        "source": "import", "raw_input": "",
    },
    {
        "id": 2, "amount": -1234.56, "currency": "RUB", "category": "groceries",
        "description": "Пятёрочка", "merchant": "Пятёрочка", "account_id": 1,
        "transaction_type": "expense", "occurred_on": "2026-03-12", "tags": "bank,ozon",
        "source": "import", "raw_input": "",
    },
    {
        "id": 3, "amount": 180000.0, "currency": "RUB", "category": "salary",
        "description": "Зарплата", "merchant": "", "account_id": 1,
        "transaction_type": "income", "occurred_on": "2026-03-13", "tags": "",
        "source": "import", "raw_input": "",
    },
    {
        "id": 4, "amount": -300.0, "currency": "RUB", "category": "cafe",
        "description": "Кофе на вынос", "merchant": "Cofix", "account_id": 1,
        "transaction_type": "expense", "occurred_on": "2026-02-02", "tags": "",
        "source": "manual", "raw_input": "",
    },
]

ACCOUNTS = [
    {"id": 1, "name": "Ozon Банк", "account_type": "bank", "balance": 226635.94, "currency": "RUB"},
    {"id": 2, "name": "Наличные", "account_type": "cash", "balance": 10000.0, "currency": "RUB"},
]


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/transactions") and request.method == "GET":
        return httpx.Response(200, json=TRANSACTIONS)
    if path.endswith("/transactions/quick"):
        return httpx.Response(
            200,
            json={
                "parsed": {"amount": -450.0, "category": "cafe"},
                "confidence": 0.92,
                "explanation": "Расход",
                "needs_confirmation": False,
            },
        )
    if path.endswith("/accounts"):
        return httpx.Response(200, json=ACCOUNTS)
    if path.endswith("/dashboard"):
        return httpx.Response(
            200,
            json={
                "balances": {"total": 236635.94, "income_month": 180000, "expense_month": 1984.56},
                "health_score": {"score": 78},
                "net_worth": {"current": 736635.94},
                "insights": [{"title": "Кофе дорожает"}],
                "streak_days": 5,
                "profile": {"name": "Кирилл"},
                "extra_noise": "should be dropped",
            },
        )
    if path.endswith("/connections"):
        return httpx.Response(
            200,
            json=[{"id": 1, "provider": "ozon", "title": "Ozon Банк", "status": "idle"}],
        )
    if path.endswith("/statement"):
        return httpx.Response(200, json={"imported_count": 5, "duplicate_count": 0})
    if path.endswith("/sync"):
        payload = json.loads(request.content or b"{}")
        return httpx.Response(200, json={"echo_since": payload.get("since")})
    if path.endswith("/networth"):
        return httpx.Response(200, json={"current": 736635.94})
    return httpx.Response(404, json={"detail": f"unexpected {path}"})


@pytest.fixture
def api_client() -> FinanceApiClient:
    return FinanceApiClient(
        "http://finance.test/api/v1", transport=httpx.MockTransport(_handler)
    )


# --- tool contract ----------------------------------------------------------


def test_tool_names_are_unique():
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_tool_schema_is_well_formed(tool):
    schema = tool.input_schema
    assert schema["type"] == "object"
    assert isinstance(schema["properties"], dict)
    # Every required argument must actually be declared.
    assert set(schema["required"]) <= set(schema["properties"])
    for name, spec in schema["properties"].items():
        assert "type" in spec, f"{tool.name}.{name} has no type"
    assert len(tool.description) > 30, f"{tool.name} needs a usable description"


def test_descriptors_use_the_wire_field_name():
    descriptors = tool_descriptors()
    assert len(descriptors) == len(TOOLS)
    assert all("inputSchema" in d for d in descriptors)
    assert {d["name"] for d in descriptors} == set(TOOLS_BY_NAME)


# --- protocol ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_echoes_supported_protocol(api_client):
    server = McpStdioServer(api_client)
    response = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}},
        }
    )
    result = response["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["serverInfo"]["name"] == "personal-finance-ai"
    assert "search_transactions" in result["instructions"]


@pytest.mark.asyncio
async def test_initialize_falls_back_for_unknown_protocol(api_client):
    response = await McpStdioServer(api_client).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
    )
    assert response["result"]["protocolVersion"] == "2025-06-18"


@pytest.mark.asyncio
async def test_notifications_get_no_response(api_client):
    assert await McpStdioServer(api_client).handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


@pytest.mark.asyncio
async def test_unknown_method_returns_method_not_found(api_client):
    response = await McpStdioServer(api_client).handle(
        {"jsonrpc": "2.0", "id": 7, "method": "resources/list"}
    )
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_tools_list_exposes_every_tool(api_client):
    response = await McpStdioServer(api_client).handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert len(response["result"]["tools"]) == len(TOOLS)


@pytest.mark.asyncio
async def test_tools_call_returns_text_content(api_client):
    response = await McpStdioServer(api_client).handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_accounts", "arguments": {}},
        }
    )
    result = response["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["total"] == 236635.94
    assert len(payload["accounts"]) == 2


@pytest.mark.asyncio
async def test_unknown_tool_is_a_tool_error_not_a_protocol_error(api_client):
    response = await McpStdioServer(api_client).handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "drop_database", "arguments": {}},
        }
    )
    assert "error" not in response
    assert response["result"]["isError"] is True
    assert "Неизвестный инструмент" in response["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_missing_required_argument_is_reported_to_the_model(api_client):
    response = await McpStdioServer(api_client).handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "list_bank_imports", "arguments": {}},
        }
    )
    assert response["result"]["isError"] is True
    assert "connection_id" in response["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_api_outage_surfaces_as_tool_error():
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    server = McpStdioServer(
        FinanceApiClient("http://down.test/api/v1", transport=httpx.MockTransport(refuse))
    )
    response = await server.handle(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "list_accounts"}}
    )
    assert response["result"]["isError"] is True
    assert "FINANCE_API_URL" in response["result"]["content"][0]["text"]


# --- handlers ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_transactions_aggregates_by_category(api_client):
    result = await call_tool(api_client, "search_transactions", {"since": "2026-03-01"})

    assert result["count"] == 3
    assert result["total_spent"] == 1684.56
    assert result["total_received"] == 180000.0
    assert result["net"] == 178315.44
    assert result["spent_by_category"] == {"groceries": 1234.56, "cafe": 450.0}
    # Highest spend first, so the model reads the answer off the top.
    assert list(result["spent_by_category"]) == ["groceries", "cafe"]


@pytest.mark.asyncio
async def test_search_transactions_filters_by_text_and_type(api_client):
    result = await call_tool(
        api_client, "search_transactions", {"query": "кофе", "transaction_type": "expense"}
    )
    assert result["count"] == 1
    assert result["transactions"][0]["merchant"] == "Cofix"


@pytest.mark.asyncio
async def test_search_transactions_filters_by_category_and_amount(api_client):
    result = await call_tool(
        api_client, "search_transactions", {"category": "cafe", "min_amount": 400}
    )
    assert result["count"] == 1
    assert result["transactions"][0]["id"] == 1


@pytest.mark.asyncio
async def test_search_transactions_caps_returned_rows(api_client):
    result = await call_tool(api_client, "search_transactions", {"limit": 1})
    assert len(result["transactions"]) == 1
    assert result["truncated"] is True
    # Aggregates still cover everything, not just the returned page.
    assert result["count"] == 4


@pytest.mark.asyncio
async def test_overview_drops_unused_dashboard_noise(api_client):
    result = await call_tool(api_client, "get_financial_overview", {})
    assert result["health_score"] == {"score": 78}
    assert "extra_noise" not in result


@pytest.mark.asyncio
async def test_add_transaction_requires_text(api_client):
    with pytest.raises(FinanceApiError, match="текст операции"):
        await call_tool(api_client, "add_transaction", {"text": "  "})


@pytest.mark.asyncio
async def test_add_transaction_passes_text_through(api_client):
    result = await call_tool(api_client, "add_transaction", {"text": "-450 кофе"})
    assert result["parsed"]["category"] == "cafe"


@pytest.mark.asyncio
async def test_sync_defaults_to_a_ninety_day_window(api_client):
    result = await call_tool(api_client, "sync_bank_connection", {"connection_id": 1})
    since = date.fromisoformat(result["echo_since"])
    assert (date.today() - since) == timedelta(days=90)


@pytest.mark.asyncio
async def test_import_statement_rejects_a_missing_file(api_client, tmp_path):
    with pytest.raises(FinanceApiError, match="не найден"):
        await call_tool(
            api_client,
            "import_bank_statement",
            {"connection_id": 1, "file_path": str(tmp_path / "nope.csv")},
        )


@pytest.mark.asyncio
async def test_import_statement_uploads_the_file(api_client, tmp_path):
    path = tmp_path / "march.csv"
    path.write_text("Дата операции;Сумма операции\n12.03.2026;-100\n", encoding="utf-8")

    result = await call_tool(
        api_client, "import_bank_statement", {"connection_id": 1, "file_path": str(path)}
    )
    assert result["imported_count"] == 5
