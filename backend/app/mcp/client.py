"""HTTP client the MCP server uses to talk to the finance API.

Going over HTTP rather than straight into SQLite is deliberate: the MCP server
normally runs on the laptop where Claude Desktop / Cursor lives, while the app
itself runs on a server. It also means every MCP call goes through the same
validation and business logic as the web UI.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


class FinanceApiError(RuntimeError):
    """The finance API is unreachable or refused the request."""


class FinanceApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("FINANCE_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or os.getenv("FINANCE_API_TOKEN", "")
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise FinanceApiError(
                f"Не удалось связаться с финансовым API по адресу {self.base_url}: {exc}. "
                "Проверьте, что приложение запущено и переменная FINANCE_API_URL верна."
            ) from exc

        if response.status_code >= 400:
            raise FinanceApiError(
                f"{method} {path} → {response.status_code}: {response.text[:400]}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._request("GET", path, params=clean or None)

    async def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json=payload or {})

    async def upload(self, path: str, filename: str, data: bytes) -> Any:
        return await self._request(
            "POST", path, files={"file": (filename, data, "application/octet-stream")}
        )
