"""Локальный шлюз Cursor говорит и JSON, и SSE: Hermes всегда открывает stream."""
import json
import threading
import urllib.error
import urllib.request

import cursor_gateway


def _server(monkeypatch, answer="ок"):
    monkeypatch.setattr(cursor_gateway, "GATEWAY_KEY", "test-key")
    monkeypatch.setattr(cursor_gateway, "_ask", lambda model, prompt: (0, answer))
    server = cursor_gateway.ThreadingHTTPServer(("127.0.0.1", 0), cursor_gateway.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _post(server, payload, key="test-key"):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def test_stream_ends_with_finish_reason(monkeypatch):
    server = _server(monkeypatch)
    try:
        status, content_type, raw = _post(server, {
            "model": "cursor-grok-4.6-high-fast",
            "stream": True,
            "messages": [{"role": "user", "content": "Привет"}],
        })
    finally:
        server.shutdown()
    text = raw.decode()
    assert status == 200
    assert content_type.startswith("text/event-stream")
    assert '"content": "ок"' in text
    assert '"finish_reason": "stop"' in text
    assert text.strip().endswith("data: [DONE]")


def test_plain_completion_keeps_the_message(monkeypatch):
    server = _server(monkeypatch, answer="готово")
    try:
        status, content_type, raw = _post(server, {
            "model": "m",
            "messages": [{"role": "user", "content": "да"}],
        })
    finally:
        server.shutdown()
    body = json.loads(raw)
    assert status == 200
    assert content_type.startswith("application/json")
    assert body["choices"][0]["message"]["content"] == "готово"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_wrong_key_is_unauthorized(monkeypatch):
    server = _server(monkeypatch)
    try:
        _post(server, {"messages": [{"role": "user", "content": "x"}]}, key="no-key-required")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
        assert json.loads(exc.read())["error"]["message"] == "unauthorized"
    else:
        raise AssertionError("expected 401")
    finally:
        server.shutdown()
