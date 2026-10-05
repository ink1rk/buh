import anyio
import httpx2 as httpx
import pytest
from urllib.parse import unquote

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


def test_tools_are_read_only():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.method)

    server = create_server(client=client_for(handler))
    tools = anyio.run(server.list_tools)
    names = {tool.name for tool in tools}
    assert {"onec_list", "onec_get", "onec_count"} <= names
    assert not names & {"onec_create", "onec_update", "onec_post_document", "onec_unpost_document"}
    assert all(tool.annotations is not None and tool.annotations.read_only_hint for tool in tools)
