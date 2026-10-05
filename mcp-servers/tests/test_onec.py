import anyio
import httpx2 as httpx
import pytest
from urllib.parse import unquote
from mcp.server.mcpserver.exceptions import ToolError

from mcp_common.errors import IntegrationError
from onec.client import OneCClient
from onec.server import create_server

GUID = "11111111-2222-3333-4444-555555555555"


def client_for(handler) -> OneCClient:
    return OneCClient(
        "http://onec.local/acc/odata/standard.odata",
        "mcp",
        "secret",
        http_service_url="http://onec.local/acc/hs/exchange",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_list_sends_odata_query_and_rejects_path_escape():
    def handler(request: httpx.Request) -> httpx.Response:
        if "$orderby" in request.url.params:
            assert request.url.params["$orderby"] == "Description desc"
            return httpx.Response(200, json={"value": []})
        assert request.url.params["$filter"] == "Description eq 'Ромашка'"
        assert request.url.params["$top"] == "20"
        assert unquote(request.url.path).endswith("/Catalog_Контрагенты")
        return httpx.Response(200, json={"value": [{"Description": "Ромашка", "Ref_Key": GUID}]})

    onec = client_for(handler)
    listed = onec.list_objects("Catalog_Контрагенты", filter="Description eq 'Ромашка'")
    assert listed["items"][0]["Ref_Key"] == GUID
    assert onec.list_objects("Catalog_Контрагенты", orderby="Description desc")["count"] == 0
    with pytest.raises(IntegrationError, match="сущности"):
        onec.list_objects("Catalog_X/../../win")
    with pytest.raises(IntegrationError, match="путь"):
        onec.call_http("../admin")
    with pytest.raises(IntegrationError, match="путь"):
        onec.call_http("https://evil.example/steal")


def test_embedded_credentials_in_url_are_rejected():
    with pytest.raises(IntegrationError, match="без логина"):
        OneCClient("http://user:pass@onec.local/acc/odata/standard.odata", "mcp", "secret")


def test_create_is_off_until_writes_enabled(monkeypatch):
    monkeypatch.delenv("MCP_ENABLE_WRITES", raising=False)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("POST не должен уходить, пока запись выключена")

    server = create_server(client=client_for(handler))
    with pytest.raises(ToolError, match="MCP_ENABLE_WRITES"):
        anyio.run(
            server.call_tool,
            "onec_create",
            {"entity": "Catalog_Контрагенты", "payload_json": '{"Description":"Ромашка"}'},
        )

    monkeypatch.setenv("MCP_ENABLE_WRITES", "true")
    seen: list[httpx.Request] = []

    def allow(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Ref_Key": GUID})

    server = create_server(client=client_for(allow))
    result = anyio.run(
        server.call_tool,
        "onec_create",
        {"entity": "Catalog_Контрагенты", "payload_json": '{"Description":"Ромашка"}'},
    )
    assert result.is_error is False
    assert seen[0].method == "POST"
    assert GUID in result.content[0].text
