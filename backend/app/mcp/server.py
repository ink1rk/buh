"""MCP server exposing the finance app to AI assistants.

Speaks the Model Context Protocol (JSON-RPC 2.0) directly. Implementing the
three methods we need — `initialize`, `tools/list`, `tools/call` — keeps the
only runtime dependency `httpx`, which the backend already has, and avoids
breaking every time the MCP SDK reshuffles its API.

`handle` knows nothing about transports: desktop clients get it over stdio via
`serve_stdio`, and JARVIS gets the same messages over HTTP from
`app.api.routes.mcp`.

Run it from an assistant config:

    {
      "mcpServers": {
        "finance": {
          "command": "python",
          "args": ["-m", "app.mcp.server"],
          "cwd": "/opt/personal-finance-ai/backend",
          "env": {"FINANCE_API_URL": "http://127.0.0.1:8000/api/v1"}
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from app.mcp.client import FinanceApiClient, FinanceApiError
from app.mcp.tools import TOOLS, call_tool

SERVER_NAME = "personal-finance-ai"
SERVER_VERSION = "1.0.0"
PREFERRED_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "Финансовый штаб пользователя: счета, операции, цели, капитал и подключения к банкам. "
    "Суммы в рублях; расходы отрицательные, доходы положительные. "
    "Перед выводами вызовите get_financial_overview, чтобы увидеть текущую картину, "
    "а для конкретных вопросов о тратах — search_transactions, он уже возвращает итоги "
    "и разбивку по категориям."
)

logger = logging.getLogger("finance-mcp")


def tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            # Клиент решает по этой пометке, можно ли звать инструмент без
            # подтверждения владельца. Поэтому её выставляет сервер, а не он.
            "annotations": {"readOnlyHint": not tool.writes},
        }
        for tool in TOOLS
    ]


class McpServer:
    def __init__(self, client: FinanceApiClient | None = None) -> None:
        self._client = client or FinanceApiClient()

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message. Returns None for notifications."""
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params") or {}

        # Notifications carry no id and must never be answered.
        if message_id is None:
            return None

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tool_descriptors()}
            elif method == "tools/call":
                result = await self._call_tool(params)
            else:
                return _error(message_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # noqa: BLE001 - never kill the session
            logger.exception("Unhandled error in %s", method)
            return _error(message_id, -32603, f"Internal error: {exc}")

        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = str(params.get("protocolVersion") or "")
        version = requested if requested in SUPPORTED_PROTOCOLS else PREFERRED_PROTOCOL
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }

    async def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _tool_error("Аргументы инструмента должны быть объектом")

        try:
            payload = await call_tool(self._client, name, arguments)
        except FinanceApiError as exc:
            return _tool_error(str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            return _tool_error(f"Некорректные аргументы для «{name}»: {exc}")

        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    async def serve_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            line = line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _write(_error(None, -32700, "Parse error"))
                continue

            if isinstance(message, list):
                for item in message:
                    response = await self.handle(item)
                    if response is not None:
                        _write(response)
                continue

            response = await self.handle(message)
            if response is not None:
                _write(response)


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict[str, Any]:
    # Tool failures are results, not protocol errors, so the model can react.
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    # stdout is the protocol channel — logging must go to stderr.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    client = FinanceApiClient()
    logger.info("Finance MCP server started, API=%s", client.base_url)
    try:
        asyncio.run(McpServer(client).serve_stdio())
    except KeyboardInterrupt:  # pragma: no cover
        pass


if __name__ == "__main__":
    main()
