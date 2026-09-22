#!/usr/bin/env python3
"""Клиент MCP: как ядро спрашивает внешние сервисы.

Мост с телефоном, а завтра — календарь, дом, машина: у каждого свои данные и
свой процесс. Тянуть их внутрь ядра значит превращать его в свалку, поэтому
они подключаются одинаково — как MCP-серверы, — и ядро знает про них ровно
две вещи: адрес и токен.

Шлюз MCP сюда вписывается без единой правки: он выглядит как ещё один
сервер, просто отдаёт инструменты нескольких сервисов сразу.

Клиент говорит на обеих эпохах протокола. Сначала пробует `2026-07-28` —
запрос без сессии, версия в `_meta`, метод и имя в заголовках. Если сервер
старый, происходит обычное рукопожатие `initialize`, и дальше запросы идут
с его идентификатором сессии.
"""
import base64
import itertools
import threading
import time

import httpx

from .config import config

LATEST = "2026-07-28"
LEGACY_PREFERRED = "2025-06-18"

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT = "io.modelcontextprotocol/clientInfo"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"

UNSUPPORTED_PROTOCOL_VERSION = -32022
NAMED_METHODS = {"tools/call": "name", "resources/read": "uri", "prompts/get": "name"}

CLIENT_INFO = {"name": "jarvis-core", "version": "1.0"}


class McpError(RuntimeError):
    """Сервер недоступен или ответил ошибкой протокола.

    `retryable` отделяет «сеть моргнула» от «сервер сказал нет»: первое стоит
    повторить, второе — нет, иначе одно напоминание уедет на телефон трижды.
    """

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def _header_value(value):
    text = str(value)
    if all(0x20 <= ord(c) <= 0x7E for c in text) and text == text.strip():
        return text
    return "=?base64?" + base64.b64encode(text.encode()).decode() + "?="


class McpClient:
    def __init__(self, name, url, token="", timeout=None, transport=None):
        self.name = name
        self.url = url
        self.token = token
        self.timeout = timeout or config.mcp.timeout
        self.transport = transport
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._version = None
        self._session = None
        self._tools = None

    # -- транспорт -------------------------------------------------------
    def _post(self, body, headers):
        kwargs = {"timeout": self.timeout, "trust_env": False}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        try:
            with httpx.Client(**kwargs) as client:
                return client.post(self.url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise McpError(f"{self.name}: {type(e).__name__}: {e}", retryable=True) from e

    def _rpc(self, method, params, version, notification=False):
        """(результат, ошибка, ответ). Ошибку разбирает вызывающий."""
        params = dict(params or {})
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": version}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if version == LATEST:
            params["_meta"] = {META_VERSION: version, META_CLIENT: CLIENT_INFO,
                               META_CAPABILITIES: {}}
            headers["Mcp-Method"] = method
            target = params.get(NAMED_METHODS.get(method, ""))
            if target is not None:
                headers["Mcp-Name"] = _header_value(target)
        elif self._session:
            headers["Mcp-Session-Id"] = self._session

        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            body["id"] = next(self._ids)

        response = self._post(body, headers)
        if notification:
            return None, None, response
        try:
            payload = response.json()
        except ValueError:
            raise McpError(f"{self.name}: ответ не JSON (HTTP {response.status_code})")
        return payload.get("result"), payload.get("error"), response

    # -- согласование версии ---------------------------------------------
    def _prepare(self):
        if self._version:
            return self._version
        with self._lock:
            if self._version:
                return self._version
            result, error, _ = self._rpc("server/discover", {}, LATEST)
            if result is not None:
                supported = result.get("supportedVersions") or [LATEST]
                self._version = LATEST if LATEST in supported else self._handshake(
                    _best(supported))
                return self._version
            if error and error.get("code") == UNSUPPORTED_PROTOCOL_VERSION:
                supported = (error.get("data") or {}).get("supported") or []
                chosen = _best(supported)
                self._version = chosen if chosen == LATEST else self._handshake(chosen)
                return self._version
            # Сервер не знает `server/discover` — значит он старой эпохи.
            self._version = self._handshake(LEGACY_PREFERRED)
            return self._version

    def _handshake(self, version):
        """Рукопожатие старой эпохи: одно на процесс, дальше живём сессией."""
        result, error, response = self._rpc(
            "initialize", {"protocolVersion": version, "capabilities": {},
                           "clientInfo": CLIENT_INFO}, version)
        if error:
            raise McpError(f"{self.name}: initialize отклонён: {error.get('message')}")
        self._session = response.headers.get("mcp-session-id")
        agreed = (result or {}).get("protocolVersion") or version
        self._rpc("notifications/initialized", {}, agreed, notification=True)
        return agreed

    def _send(self, method, params=None):
        version = self._prepare()
        result, error, _ = self._rpc(method, params, version)
        if error:
            raise McpError(f"{self.name}: {error.get('message')} "
                           f"(код {error.get('code')})")
        return result or {}

    # -- то, ради чего всё -----------------------------------------------
    def discover(self):
        return self._send("server/discover")

    def tools(self, refresh=False):
        if self._tools is None or refresh:
            self._tools = self._send("tools/list").get("tools", [])
        return self._tools

    def resources(self):
        return self._send("resources/list").get("resources", [])

    def read(self, uri):
        contents = self._send("resources/read", {"uri": uri}).get("contents", [])
        return contents[0].get("text", "") if contents else ""

    def call(self, tool, arguments=None):
        """Результат инструмента: текст для модели, структура для интерфейса."""
        result = self._send("tools/call", {"name": tool, "arguments": arguments or {}})
        blocks = result.get("content") or []
        text = "\n".join(block.get("text", "") for block in blocks
                         if block.get("type") == "text").strip()
        return {"server": self.name, "tool": tool, "text": text,
                "data": result.get("structuredContent"),
                "is_error": bool(result.get("isError"))}

    def health(self):
        started = time.time()
        tools = self.tools(refresh=True)
        return {"ok": True, "tools": len(tools), "version": self._version,
                "ms": round((time.time() - started) * 1000)}


def _best(supported):
    """Самая новая из общих версий; пусто — считаем сервер старым."""
    for version in (LATEST, "2025-11-25", LEGACY_PREFERRED):
        if version in (supported or ()):
            return version
    return LEGACY_PREFERRED


class McpRegistry:
    """Все подключённые серверы разом — и поиск инструмента по имени."""

    def __init__(self, servers=None, client_factory=McpClient):
        entries = servers if servers is not None else config.mcp.servers
        self.clients = {entry.name: client_factory(entry.name, entry.url, entry.token)
                        for entry in entries}

    def names(self):
        return list(self.clients)

    def get(self, name):
        client = self.clients.get(name)
        if client is None:
            raise McpError(f"сервер MCP {name!r} не подключён")
        return client

    def catalogue(self, refresh=False):
        out = []
        for name, client in self.clients.items():
            item = {"name": name, "url": client.url}
            try:
                item["tools"] = [{"name": t["name"], "title": t.get("title", ""),
                                  "description": t.get("description", "")}
                                 for t in client.tools(refresh=refresh)]
                item["status"] = "ok"
            except McpError as e:
                item["tools"], item["status"], item["error"] = [], "error", str(e)
            out.append(item)
        return out

    def call(self, server, tool, arguments=None):
        return self.get(server).call(tool, arguments)

    def find(self, suffix):
        """(сервер, точное имя). Шлюз отдаёт те же инструменты с приставкой."""
        for name, client in self.clients.items():
            try:
                names = [t["name"] for t in client.tools()]
            except McpError:
                continue
            for tool in names:
                if tool == suffix or tool.endswith(f".{suffix}") \
                        or tool.endswith(f"_{suffix}") or tool.endswith(f"/{suffix}"):
                    return name, tool
        return None, None

    def call_tool(self, suffix, arguments=None):
        """Позвать инструмент, не зная, за каким сервером он сейчас живёт."""
        server, tool = self.find(suffix)
        if server is None:
            raise McpError(f"инструмента {suffix!r} нет ни на одном сервере MCP")
        return self.call(server, tool, arguments)
