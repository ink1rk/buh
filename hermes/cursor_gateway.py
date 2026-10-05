#!/usr/bin/env python3
"""OpenAI-совместимый шлюз к Cursor CLI. Слушает только localhost:8791.

Ключ Cursor — CURSOR_API_KEY. Клиенты (ассистент, Hermes) приходят со своим
ключом GATEWAY_KEY. Режимы ask: модель отвечает, файлы на диске не меняет.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "").strip()
CURSOR_BIN = os.environ.get("CURSOR_AGENT", "agent")
DEFAULT_MODEL = os.environ.get("GATEWAY_MODEL", "cursor-grok-4.6-high-fast")
PORT = int(os.environ.get("GATEWAY_PORT", "8791"))
WORKSPACE = os.environ.get("CURSOR_WORKSPACE", "/var/lib/cursor-gateway")


def _prompt(messages: list) -> str:
    lines = []
    for message in messages:
        role = message.get("role") or "user"
        content = message.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _completion(model: str, text: str) -> dict:
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
    }


def _sse(model: str, text: str) -> bytes:
    """OpenAI chat stream. Hermes opens stream=True and treats a bare JSON
    body as an empty stream with no finish_reason."""
    created = int(time.time())

    def chunk(delta: dict, finish: str | None) -> bytes:
        payload = {
            "id": "chatcmpl-local",
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n"

    return b"".join((
        chunk({"role": "assistant", "content": text}, None),
        chunk({}, "stop"),
        b"data: [DONE]\n\n",
    ))


def _ask(model: str, prompt: str) -> tuple[int, str]:
    env = os.environ.copy()
    proc = subprocess.run(
        [
            CURSOR_BIN, "-p", "--mode", "ask", "--trust",
            "--output-format", "text", "--model", model,
            "--workspace", WORKSPACE, prompt,
        ],
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
        try:
            code, text = _ask(model, _prompt(body.get("messages") or []))
        except subprocess.TimeoutExpired:
            self._json(504, {"error": {"message": "timeout"}})
            return
        if code != 0:
            self._json(502, {"error": {"message": text[:500]}})
            return
        if body.get("stream"):
            self._events(_sse(model, text))
            return
        self._json(200, _completion(model, text))

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
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
