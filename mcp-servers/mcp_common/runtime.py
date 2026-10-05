"""Запуск MCP по Streamable HTTP и общие правила инструментов."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_common.errors import IntegrationError

READ = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)
WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)

_MAX_CHARS = 80_000


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def writes_enabled() -> bool:
    return env_bool("MCP_ENABLE_WRITES", False)


def require_write() -> None:
    if not writes_enabled():
        raise ToolError(
            "Запись выключена. Чтобы разрешить изменяющие инструменты, "
            "установите MCP_ENABLE_WRITES=true на этом сервере."
        )


def dump(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= _MAX_CHARS:
        return text
    return json.dumps(
        {"truncated": True, "preview": text[:_MAX_CHARS]},
        ensure_ascii=False,
    )


def tool_result(producer: Callable[[], Any]) -> str:
    try:
        return dump(producer())
    except IntegrationError as exc:
        raise ToolError(str(exc)) from exc


class StaticTokenVerifier(TokenVerifier):
    """Общий секрет шлюза и MCP-сервера. Это не OAuth пользователя."""

    def __init__(self, token: str):
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or len(token) != len(self._token):
            return None
        if not secrets.compare_digest(token, self._token):
            return None
        return AccessToken(token=token, client_id="mcp-gateway", scopes=["mcp"])


def _auth_kwargs() -> dict[str, Any]:
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return {}
    return {
        "token_verifier": StaticTokenVerifier(token),
        "auth": AuthSettings(
            issuer_url=os.environ.get("MCP_ISSUER_URL", "http://mcp-gateway.local"),
            resource_server_url=os.environ.get("MCP_RESOURCE_URL", "http://127.0.0.1:8080"),
            required_scopes=["mcp"],
            validate_token_resource=False,
        ),
    }


def build_server(name: str, title: str, instructions: str) -> MCPServer:
    level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    server = MCPServer(
        name=name,
        title=title,
        instructions=instructions,
        **_auth_kwargs(),
        log_level=level,  # type: ignore[arg-type]
    )
    install_health(server)
    return server


def install_health(server: MCPServer) -> None:
    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> Response:
        return JSONResponse({"status": "ok", "server": server.name})


def serve(server: MCPServer) -> None:
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http").strip().lower()
    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport not in {"streamable-http", "http"}:
        raise SystemExit(f"Неизвестный MCP_TRANSPORT={transport}")
    server.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", "8080")),
        streamable_http_path=os.environ.get("MCP_PATH", "/mcp"),
        json_response=env_bool("MCP_JSON_RESPONSE", True),
        stateless_http=env_bool("MCP_STATELESS", True),
    )
