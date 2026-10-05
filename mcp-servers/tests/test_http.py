import json

from starlette.testclient import TestClient

from ad.client import ADClient, ADSettings
from ad.server import create_server
from tests.test_ad import ScriptedConn, user_entry

SETTINGS = ADSettings(
    server="dc.example.local",
    port=636,
    use_ssl=True,
    starttls=False,
    tls_verify=True,
    bind_user="EXAMPLE\\svc",
    bind_password="bind-secret",
    base_dn="DC=example,DC=local",
)

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def _app(monkeypatch, token: str | None = None):
    if token is None:
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MCP_AUTH_TOKEN", token)
        monkeypatch.setenv("MCP_RESOURCE_URL", "http://mcp-ad.local")
        monkeypatch.setenv("MCP_ISSUER_URL", "http://mcp-gateway.local")
    server = create_server(client=ADClient(SETTINGS, connector=lambda: ScriptedConn([[user_entry()]])))
    return server.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")


def test_health_and_initialize(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["server"] == "ad"
        response = client.post(
            "/mcp",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=_INIT,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"]["serverInfo"]["name"] == "ad"
        tools = client.post(
            "/mcp",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        names = {item["name"] for item in tools.json()["result"]["tools"]}
        assert {"ad_search_users", "ad_reset_password", "ad_ping"} <= names


def test_gateway_token_does_not_cover_health(monkeypatch):
    app = _app(monkeypatch, token="gateway-secret")
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        denied = client.post(
            "/mcp",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=_INIT,
        )
        assert denied.status_code == 401
        allowed = client.post(
            "/mcp",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer gateway-secret",
            },
            json=_INIT,
        )
        assert allowed.status_code == 200
        assert json.loads(allowed.content)["result"]["protocolVersion"] == "2025-03-26"
