"""MCP over HTTP, so the assistant can reach the finance app by address.

The stdio server exists for desktop clients that spawn a subprocess. JARVIS is
not one of them: it runs as a service on the same VM and connects to things by
URL. The protocol handling is identical either way, so only the transport lives
here.

Unlike the rest of this API, the endpoint demands a token. The reason is the
tool list: alongside the read-only overview there are tools that import
statements and touch accounts, and this app has no other authentication at all.
Without a token set the endpoint is not merely unguarded — it does not exist.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.core.config import get_settings
from app.mcp.client import FinanceApiClient
from app.mcp.server import McpServer

router = APIRouter(prefix="/mcp", tags=["mcp"])

MAX_BODY_BYTES = 256 * 1024

PARSE_ERROR = -32700
INVALID_REQUEST = -32600


def _authorise(header: str | None) -> None:
    expected = get_settings().mcp_token
    if not expected:
        raise HTTPException(404, "MCP не включён")
    supplied = (header or "").removeprefix("Bearer ").strip()
    # Сравнение постоянного времени: иначе токен подбирается по задержке ответа.
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Нужен токен MCP")


def _session(request: Request) -> McpServer:
    """Один клиент API на процесс: httpx-соединения стоит переиспользовать."""
    existing = getattr(request.app.state, "mcp_session", None)
    if existing is None:
        existing = McpServer(FinanceApiClient())
        request.app.state.mcp_session = existing
    return existing


def _reply(payload: Any) -> Response:
    return Response(content=json.dumps(payload, ensure_ascii=False),
                    media_type="application/json")


def _failed(code: int, message: str) -> Response:
    return _reply({"jsonrpc": "2.0", "id": None,
                   "error": {"code": code, "message": message}})


@router.post("")
async def mcp_endpoint(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _authorise(authorization)

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, "Слишком большой запрос")

    try:
        message = json.loads(raw or b"")
    except json.JSONDecodeError:
        return _failed(PARSE_ERROR, "Parse error")

    server = _session(request)
    if isinstance(message, list):
        answers = [answer for answer in
                   [await server.handle(item) for item in message
                    if isinstance(item, dict)]
                   if answer is not None]
        # Пачка из одних уведомлений ответа не требует, как и одно уведомление.
        return _reply(answers) if answers else Response(status_code=202)
    if not isinstance(message, dict):
        return _failed(INVALID_REQUEST, "Invalid request")

    answer = await server.handle(message)
    return _reply(answer) if answer is not None else Response(status_code=202)
