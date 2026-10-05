import anyio
import httpx2 as httpx
import pytest
from urllib.parse import unquote
from mcp.server.mcpserver.exceptions import ToolError

from exchange.ews import EwsExchange
from exchange.graph import GraphExchange
from exchange.server import create_server

_SOAP_OK = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Body>
    <m:CreateItemResponse>
      <m:ResponseMessages>
        <m:CreateItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
        </m:CreateItemResponseMessage>
      </m:ResponseMessages>
    </m:CreateItemResponse>
  </s:Body>
</s:Envelope>
"""


def test_graph_lists_messages_with_app_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        assert unquote(request.url.path) == "/v1.0/users/user@example.com/mailFolders/inbox/messages"
        return httpx.Response(
            200,
            json={"value": [{"id": "m1", "subject": "Счёт", "bodyPreview": "оплата", "from": {"emailAddress": {"address": "a@b.c"}}}]},
        )

    client = GraphExchange("tenant", "app", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
    listed = client.list_messages("user@example.com", folder="inbox", limit=5)
    assert listed["messages"][0]["subject"] == "Счёт"
    assert listed["messages"][0]["body"] is None
    assert seen[0].url.host == "login.microsoftonline.com"


def test_graph_send_stays_behind_write_flag(monkeypatch):
    monkeypatch.delenv("MCP_ENABLE_WRITES", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        raise AssertionError("отправка не должна выходить в Graph, пока запись выключена")

    graph = GraphExchange("tenant", "app", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
    server = create_server(client=graph)
    with pytest.raises(ToolError, match="MCP_ENABLE_WRITES"):
        anyio.run(
            server.call_tool,
            "exchange_send_mail",
            {"mailbox_id": "user@example.com", "to": ["a@b.c"], "subject": "hi", "body": "text"},
        )


def test_ews_escapes_subject_and_targets_mailbox():
    captured: list[str] = []

    def poster(xml: str) -> str:
        captured.append(xml)
        return _SOAP_OK

    ews = EwsExchange(
        "https://mail.example.local/EWS/Exchange.asmx",
        "EXAMPLE\\svc",
        "secret",
        auth="basic",
        impersonate=False,
        poster=poster,
    )
    ews.send_mail("user@example.com", ["finance@example.com"], "a</t:Subject>", "hello")
    xml = captured[0]
    assert "a&lt;/t:Subject&gt;" in xml
    assert "<t:EmailAddress>user@example.com</t:EmailAddress>" in xml
    assert "a</t:Subject>" not in xml
