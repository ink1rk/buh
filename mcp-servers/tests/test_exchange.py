import anyio
import httpx2 as httpx
from urllib.parse import unquote

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


def test_exchange_tools_are_read_only():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        raise AssertionError(request.url.path)

    graph = GraphExchange("tenant", "app", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
    server = create_server(client=graph)
    tools = anyio.run(server.list_tools)
    names = {tool.name for tool in tools}
    assert "exchange_list_messages" in names
    assert not names & {"exchange_send_mail", "exchange_create_event"}
    assert all(tool.annotations is not None and tool.annotations.read_only_hint for tool in tools)


def test_ews_escapes_search_and_targets_mailbox():
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
    ews.list_messages("user@example.com", query="a</t:Constant>")
    xml = captured[0]
    assert "a&lt;/t:Constant&gt;" in xml
    assert "<t:EmailAddress>user@example.com</t:EmailAddress>" in xml
    assert "a</t:Constant>" not in xml
