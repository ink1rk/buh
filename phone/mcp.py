#!/usr/bin/env python3
"""Сервер MCP: JSON-RPC без привязки к транспорту.

Одна и та же реализация отвечает и по HTTP (`POST /mcp`), и по stdio, потому
что MCP — это про сообщения, а не про сокеты.

Поддерживаются две эпохи протокола сразу:

* `2026-07-28` — без сессий: каждый запрос несёт свою версию в `_meta` и
  дублирует метод и имя в заголовках `Mcp-Method` / `Mcp-Name`. Именно это
  и позволяет поставить впереди шлюз: он маршрутизирует и авторизует по
  заголовкам, не разбирая тело.
* `2025-11-25` и `2025-06-18` — с рукопожатием `initialize`. Так пока
  разговаривает большинство готовых клиентов, и отказ от них означал бы,
  что мост не подключить ни к чему живому.

Своей реализации хватает: официальный SDK тянет полтора десятка пакетов
ради того же JSON-RPC, а сервис живёт на той же маленькой виртуалке, что и
остальное хозяйство.
"""
import base64
import binascii
import json
import sys
from dataclasses import dataclass, field

LATEST = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18")
SUPPORTED = (LATEST,) + LEGACY

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT = "io.modelcontextprotocol/clientInfo"
META_SERVER = "io.modelcontextprotocol/serverInfo"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

# Методы, у которых имя цели дублируется в заголовке `Mcp-Name`.
NAMED_METHODS = {"tools/call": "name", "resources/read": "uri", "prompts/get": "name"}

BASE64_PREFIX = "=?base64?"
BASE64_SUFFIX = "?="


class ToolError(Exception):
    """Ошибка внутри инструмента: она уезжает модели, а не в протокол."""


@dataclass
class Reply:
    """Что вернуть транспорту: код ответа и тело (для уведомлений — пусто)."""
    status: int = 200
    body: dict = None


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    handler: object
    title: str = ""
    annotations: dict = field(default_factory=dict)

    def describe(self):
        item = {"name": self.name, "description": self.description,
                "inputSchema": self.schema}
        if self.title:
            item["title"] = self.title
        if self.annotations:
            item["annotations"] = self.annotations
        return item


@dataclass
class Resource:
    uri: str
    name: str
    description: str
    reader: object
    mime_type: str = "application/json"

    def describe(self):
        return {"uri": self.uri, "name": self.name, "description": self.description,
                "mimeType": self.mime_type}


def decode_header(value):
    """`=?base64?…?=` — так в заголовок кладут то, что не влезает в ASCII."""
    if not value or not value.startswith(BASE64_PREFIX) or not value.endswith(BASE64_SUFFIX):
        return value
    payload = value[len(BASE64_PREFIX):-len(BASE64_SUFFIX)]
    try:
        return base64.b64decode(payload).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value


def no_arguments():
    return {"type": "object", "additionalProperties": False}


class Server:
    def __init__(self, name, version, instructions=""):
        self.name = name
        self.version = version
        self.instructions = instructions
        self.tools = {}
        self.resources = {}

    # -- регистрация ----------------------------------------------------
    def tool(self, name, description, schema=None, title="", annotations=None):
        def register(handler):
            self.tools[name] = Tool(name=name, description=description,
                                    schema=schema or no_arguments(), handler=handler,
                                    title=title, annotations=annotations or {})
            return handler
        return register

    def resource(self, uri, name, description, mime_type="application/json"):
        def register(reader):
            self.resources[uri] = Resource(uri=uri, name=name, description=description,
                                           reader=reader, mime_type=mime_type)
            return reader
        return register

    def capabilities(self):
        return {"tools": {"listChanged": False}, "resources": {"listChanged": False}}

    # -- разбор запроса --------------------------------------------------
    def handle(self, message, headers=None, transport="stdio"):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return Reply(400, _error(None, INVALID_REQUEST, "не JSON-RPC 2.0"))

        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return Reply(400, _error(message_id, INVALID_REQUEST, "params должен быть объектом"))

        if message_id is None:
            # Уведомление: подтверждаем приём и молчим — отвечать нечем.
            return Reply(202, None)

        version, failure = self._version(message, params, headers, transport)
        if failure:
            return failure

        if transport == "http" and version == LATEST:
            mismatch = self._check_headers(message_id, method, params, headers)
            if mismatch:
                return mismatch

        try:
            return self._dispatch(message_id, method, params, version)
        except ToolError as e:
            return Reply(200, _error(message_id, INVALID_PARAMS, str(e)))
        except Exception as e:                      # noqa: BLE001 — иначе падает весь мост
            return Reply(200, _error(message_id, INTERNAL_ERROR, f"{type(e).__name__}: {e}"))

    def _version(self, message, params, headers, transport):
        """(версия, готовый отказ). Версия — то, на чём говорим дальше."""
        meta = params.get("_meta") or {}
        body_version = meta.get(META_VERSION)
        header_version = headers.get("mcp-protocol-version")
        message_id = message.get("id")

        if transport == "http" and body_version and header_version \
                and body_version != header_version:
            return None, Reply(400, _error(
                message_id, HEADER_MISMATCH,
                f"MCP-Protocol-Version: заголовок {header_version!r}"
                f" не совпадает с телом {body_version!r}"))

        requested = body_version or header_version
        if requested is None:
            if message.get("method") == "initialize":
                # Клиент старой эпохи: версию он называет в параметрах.
                asked = params.get("protocolVersion")
                return (asked if asked in SUPPORTED else LEGACY[0]), None
            # Без версии и без рукопожатия остаётся считать клиента старым.
            return LEGACY[0], None

        if requested not in SUPPORTED:
            return None, Reply(400, _error(
                message_id, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
                data={"supported": list(SUPPORTED), "requested": requested}))
        return requested, None

    def _check_headers(self, message_id, method, params, headers):
        """Заголовки и тело должны говорить одно и то же, иначе шлюзу верить нельзя."""
        if not headers.get("mcp-protocol-version"):
            return Reply(400, _error(message_id, HEADER_MISMATCH,
                                     "нет заголовка MCP-Protocol-Version"))
        if headers.get("mcp-method") != method:
            return Reply(400, _error(
                message_id, HEADER_MISMATCH,
                f"Mcp-Method: заголовок {headers.get('mcp-method')!r} не совпадает"
                f" с методом {method!r}"))
        field_name = NAMED_METHODS.get(method)
        if field_name:
            expected = params.get(field_name)
            presented = decode_header(headers.get("mcp-name"))
            if presented != expected:
                return Reply(400, _error(
                    message_id, HEADER_MISMATCH,
                    f"Mcp-Name: заголовок {presented!r} не совпадает"
                    f" с {field_name} {expected!r}"))
        return None

    # -- методы ----------------------------------------------------------
    def _dispatch(self, message_id, method, params, version):
        if method == "server/discover":
            return self._ok(message_id, version, {
                "supportedVersions": list(SUPPORTED),
                "capabilities": self.capabilities(),
                "instructions": self.instructions,
            }, ttl_ms=3_600_000)

        if method == "initialize":
            if version == LATEST:
                return Reply(404, _error(message_id, METHOD_NOT_FOUND,
                                         f"initialize убран в {LATEST};"
                                         f" поддерживаются версии: {', '.join(SUPPORTED)}"))
            return Reply(200, _result(message_id, {
                "protocolVersion": version,
                "capabilities": self.capabilities(),
                "serverInfo": {"name": self.name, "version": self.version},
                "instructions": self.instructions,
            }))

        if method == "ping":
            return self._ok(message_id, version, {})

        if method == "tools/list":
            return self._ok(message_id, version,
                            {"tools": [t.describe() for t in self.tools.values()]},
                            ttl_ms=300_000)

        if method == "tools/call":
            return self._call_tool(message_id, params, version)

        if method == "resources/list":
            return self._ok(message_id, version,
                            {"resources": [r.describe() for r in self.resources.values()]},
                            ttl_ms=300_000)

        if method == "resources/read":
            return self._read_resource(message_id, params, version)

        return Reply(404, _error(message_id, METHOD_NOT_FOUND, f"метод {method!r} не поддерживается"))

    def _call_tool(self, message_id, params, version):
        name = params.get("name")
        tool = self.tools.get(name)
        if tool is None:
            # «Инструмент не найден» — ошибка протокола, а не результат вызова.
            return Reply(200, _error(message_id, INVALID_PARAMS,
                                     f"инструмента {name!r} нет"))
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return Reply(200, _error(message_id, INVALID_PARAMS,
                                     "arguments должен быть объектом"))
        try:
            outcome = tool.handler(**arguments) or {}
        except TypeError as e:
            return Reply(200, _error(message_id, INVALID_PARAMS, str(e)))
        except ToolError as e:
            # Ошибку самого инструмента модель должна увидеть и исправить.
            return self._ok(message_id, version,
                            {"content": [_text(str(e))], "isError": True})
        text = outcome.get("text") or ""
        data = outcome.get("data")
        result = {"content": [_text(text)], "isError": False}
        if data is not None:
            result["structuredContent"] = data
        return self._ok(message_id, version, result)

    def _read_resource(self, message_id, params, version):
        uri = params.get("uri")
        resource = self.resources.get(uri)
        if resource is None:
            return Reply(200, _error(message_id, INVALID_PARAMS, f"ресурса {uri!r} нет"))
        payload = resource.reader()
        text = payload if isinstance(payload, str) else json.dumps(
            payload, ensure_ascii=False, indent=2, default=str)
        return self._ok(message_id, version, {
            "contents": [{"uri": uri, "mimeType": resource.mime_type, "text": text}],
        }, ttl_ms=60_000, cache_scope="private")

    def _ok(self, message_id, version, payload, ttl_ms=None, cache_scope="private"):
        result = dict(payload)
        if version == LATEST:
            result["resultType"] = "complete"
            result["_meta"] = {META_SERVER: {"name": self.name, "version": self.version}}
            if ttl_ms is not None:
                result["ttlMs"] = ttl_ms
                result["cacheScope"] = cache_scope
        return Reply(200, _result(message_id, result))


def _text(value):
    return {"type": "text", "text": value}


def _result(message_id, result):
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": message_id, "error": error}


# --- stdio ---------------------------------------------------------------
def serve_stdio(server, stdin=None, stdout=None):
    """Тот же сервер, но для клиентов, которые запускают процесс сами."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _write(stdout, _error(None, PARSE_ERROR, "не разобрать JSON"))
            continue
        reply = server.handle(message, transport="stdio")
        if reply.body is not None:
            _write(stdout, reply.body)


def _write(stream, payload):
    stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    stream.flush()


def client_meta(version=LATEST, name="jarvis", client_version="1.0"):
    """`_meta` для запроса: клиент обязан называть версию на каждом запросе."""
    return {META_VERSION: version, META_CLIENT: {"name": name, "version": client_version},
            "io.modelcontextprotocol/clientCapabilities": {}}


def request_headers(method, version=LATEST, name=None):
    """Заголовки, по которым шлюз маршрутизирует запрос, не читая тело."""
    headers = {"MCP-Protocol-Version": version, "Mcp-Method": method,
               "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if name is not None:
        headers["Mcp-Name"] = _header_value(name)
    return headers


def _header_value(value):
    text = str(value)
    safe = all(0x20 <= ord(c) <= 0x7E for c in text) and text == text.strip()
    if safe and not (text.startswith(BASE64_PREFIX) and text.endswith(BASE64_SUFFIX)):
        return text
    return BASE64_PREFIX + base64.b64encode(text.encode()).decode() + BASE64_SUFFIX
