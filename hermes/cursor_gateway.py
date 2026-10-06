#!/usr/bin/env python3
"""OpenAI-совместимый шлюз к Cursor CLI. Слушает только localhost:8791.

Ключ Cursor — CURSOR_API_KEY. Клиенты (ассистент, Hermes) приходят со своим
ключом GATEWAY_KEY. CLI запускается в режиме ask: модель отвечает, файлы на
диске не меняет. Если Hermes прислал инструменты, шлюз просит у модели JSON
с tool_calls и отдаёт его обратно. Сами инструменты выполняет Hermes.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "").strip()
CURSOR_BIN = os.environ.get("CURSOR_AGENT", "agent")
DEFAULT_MODEL = os.environ.get("GATEWAY_MODEL", "cursor-grok-4.6-high-fast")
PORT = int(os.environ.get("GATEWAY_PORT", "8791"))
WORKSPACE = os.environ.get("CURSOR_WORKSPACE", "/var/lib/cursor-gateway")

TOOL_CONTRACT = """Инструменты почты, календаря, заметок, Telegram и голоса доступны тебе как MCP.
Вызывай их сам и потом ответь владельцу по-русски.
Шелл, запись файлов и чужие серверы MCP не используй.
Если инструмент вернул данные, перескажи их. Не выдумывай письма и встречи.
"""

# Шелл и запись закрыты, даже если запуск с --force: deny сильнее allow.
# Чтение секретов модели тоже закрыто. Сам процесс MCP читает их сам.
DESK_DENY = (
    "Shell(*)",
    "Write(**)",
    "Read(/etc/**)",
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/*env)",
)
DESK_MCP = ("yandex", "gmail", "calendar", "notes", "telegram", "voice")


def _text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
        return "\n".join(parts)
    return str(content)


def _render(message: dict) -> str:
    role = message.get("role") or "user"
    content = _text(message.get("content"))
    calls = message.get("tool_calls") or []
    if calls:
        rendered = []
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name") or call.get("name") or ""
            arguments = function.get("arguments")
            if arguments is None:
                arguments = call.get("arguments") or {}
            rendered.append(f"{name} {arguments}")
        extra = "вызовы: " + "; ".join(rendered)
        content = f"{content}\n{extra}".strip()
    if role == "tool":
        name = message.get("name") or message.get("tool_call_id") or "tool"
        return f"результат {name}: {content}"
    return f"{role}: {content}"


def _specs(tools: list) -> list:
    specs = []
    for tool in tools:
        function = tool.get("function") or tool
        name = function.get("name")
        if not name:
            continue
        specs.append({
            "name": name,
            "description": function.get("description") or "",
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        })
    return specs


def _prompt(messages: list, tools: list | None = None) -> str:
    dialogue = "\n".join(_render(message) for message in messages)
    specs = _specs(tools or [])
    if not specs:
        return dialogue
    names = ", ".join(spec["name"] for spec in specs)
    return TOOL_CONTRACT + "Имена инструментов: " + names + "\n\nДиалог:\n" + dialogue


def _server(kind: str) -> dict:
    env = {
        "PYTHONPATH": "/opt/assistant/hermes:/opt/assistant/assistant:/opt/assistant",
        "TZ_NAME": "Europe/Moscow",
    }
    if kind in ("yandex", "gmail", "calendar"):
        env["ASSISTANT_ENV_FILE"] = "/etc/assistant.env"
    if kind == "calendar":
        env["HTTP_PROXY"] = "http://172.20.20.231:8080"
        env["HTTPS_PROXY"] = "http://172.20.20.231:8080"
        env["NO_PROXY"] = "localhost,127.0.0.1,::1,172.20.20.0/24,10.0.0.0/8,192.168.0.0/16,.lan"
    if kind == "notes":
        env["OBSIDIAN_VAULT_PATH"] = "/opt/assistant/hermes/vault"
    if kind == "telegram":
        env["TG_USER_URL"] = "http://127.0.0.1:8810"
    if kind == "voice":
        env["EDGE_TTS_VOICE"] = "ru-RU-DmitryNeural"
        env["HTTP_PROXY"] = "http://172.20.20.231:8080"
        env["HTTPS_PROXY"] = "http://172.20.20.231:8080"
        env["NO_PROXY"] = "localhost,127.0.0.1,::1,172.20.20.0/24,10.0.0.0/8,192.168.0.0/16,.lan"
    return {
        "command": "/opt/assistant/.venv/bin/python",
        "args": ["-m", "desk_mcp", kind],
        "env": env,
    }


def ensure_workspace() -> None:
    """Каталог шлюза: MCP стола и запрет шелла. Паролей здесь нет."""
    root = os.path.join(WORKSPACE, ".cursor")
    os.makedirs(root, exist_ok=True)
    servers = {name: _server(name) for name in DESK_MCP}
    with open(os.path.join(root, "mcp.json"), "w", encoding="utf-8") as handle:
        json.dump({"mcpServers": servers}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    policy = {
        "permissions": {
            "allow": [f"Mcp({name}:*)" for name in DESK_MCP],
            "deny": list(DESK_DENY),
        }
    }
    with open(os.path.join(root, "cli.json"), "w", encoding="utf-8") as handle:
        json.dump(policy, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _payloads(text: str) -> list:
    decoder = json.JSONDecoder()
    found = []
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(obj, dict) and ("tool_calls" in obj or "content" in obj):
            found.append(obj)
        index = start + max(end, 1)
    return found


def _arguments(value) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
        except json.JSONDecodeError:
            return json.dumps({"value": value}, ensure_ascii=False)
        return value
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False)


def _tool_calls(raw) -> list:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    calls = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = function.get("name") or item.get("name") or ""
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = function.get("arguments")
        if arguments is None:
            arguments = item.get("arguments")
        calls.append({
            "id": item.get("id") or f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": name.strip(), "arguments": _arguments(arguments)},
        })
    return calls


def interpret(text: str, tools_requested: bool) -> tuple[dict, str]:
    """Ответ CLI → сообщение OpenAI. Без инструментов текст не разбирается."""
    if not tools_requested:
        return {"role": "assistant", "content": text}, "stop"
    chosen = None
    for payload in _payloads(text):
        if payload.get("tool_calls"):
            chosen = payload
            break
        chosen = chosen or payload
    calls = _tool_calls((chosen or {}).get("tool_calls"))
    if calls:
        content = (chosen or {}).get("content")
        message = {
            "role": "assistant",
            "content": content if isinstance(content, str) and content else None,
            "tool_calls": calls,
        }
        return message, "tool_calls"
    if chosen and isinstance(chosen.get("content"), str):
        return {"role": "assistant", "content": chosen["content"]}, "stop"
    return {"role": "assistant", "content": text}, "stop"


def _completion(model: str, message: dict, finish: str) -> dict:
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish,
        }],
    }


def _sse(model: str, message: dict, finish: str) -> bytes:
    """Один кусок и finish_reason. Hermes иначе считает поток пустым."""
    created = int(time.time())

    def chunk(delta: dict, reason: str | None) -> bytes:
        payload = {
            "id": "chatcmpl-local",
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
        }
        return b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n"

    delta = {"role": "assistant"}
    if message.get("content"):
        delta["content"] = message["content"]
    if message.get("tool_calls"):
        delta["tool_calls"] = [
            {"index": index, **call} for index, call in enumerate(message["tool_calls"])
        ]
    return b"".join((
        chunk(delta, None),
        chunk({}, finish),
        b"data: [DONE]\n\n",
    ))


def _command(model: str, prompt: str, use_mcp: bool) -> list:
    """ask — болтовня без диска. С инструментами MCP выполняет сам агент, не шелл."""
    if use_mcp:
        return [
            CURSOR_BIN, "-p", "--trust", "--approve-mcps", "--force",
            "--sandbox", "disabled",
            "--output-format", "text", "--model", model,
            "--workspace", WORKSPACE, prompt,
        ]
    return [
        CURSOR_BIN, "-p", "--mode", "ask", "--trust",
        "--output-format", "text", "--model", model,
        "--workspace", WORKSPACE, prompt,
    ]


def _ask(model: str, prompt: str, use_mcp: bool = False) -> tuple[int, str]:
    if use_mcp:
        ensure_workspace()
        # Один аргумент длиннее ~128 КБ ядро не примет. Текст просьбы лежит в файле.
        if len(prompt) > 60_000:
            path = os.path.join(WORKSPACE, "request.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(prompt)
            prompt = (
                "Прочитай request.md в этом каталоге и выполни просьбу. "
                "Инструменты — только MCP этого стола. Шелл и запись файлов не используй. "
                "Ответь по-русски, только итогом для владельца."
            )
    env = os.environ.copy()
    proc = subprocess.run(
        _command(model, prompt, use_mcp),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    text = (proc.stdout or "").strip()
    if proc.returncode != 0 and not text:
        text = (proc.stderr or "cursor agent failed").strip()
    return proc.returncode, text


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/health":
            self._json(200, {"status": "ok"})
            return
        if path == "/v1/models":
            self._json(200, {"object": "list", "data": [{
                "id": DEFAULT_MODEL,
                "object": "model",
                "context_length": 131072,
            }]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        if not GATEWAY_KEY or self.headers.get("Authorization", "") != f"Bearer {GATEWAY_KEY}":
            self._json(401, {"error": {"message": "unauthorized"}})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "bad json"}})
            return
        model = body.get("model") or DEFAULT_MODEL
        tools = body.get("tools") or []
        use_mcp = bool(_specs(tools))
        try:
            code, text = _ask(model, _prompt(body.get("messages") or [], tools), use_mcp)
        except subprocess.TimeoutExpired:
            self._json(504, {"error": {"message": "timeout"}})
            return
        if code != 0:
            self._json(502, {"error": {"message": text[:500]}})
            return
        message, finish = interpret(text, use_mcp)
        if body.get("stream"):
            self._events(_sse(model, message, finish))
            return
        self._json(200, _completion(model, message, finish))

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _events(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    os.makedirs(WORKSPACE, exist_ok=True)
    ensure_workspace()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
