"""Локальный шлюз Cursor говорит и JSON, и SSE: Hermes всегда открывает stream."""
import json
import threading
import urllib.error
import urllib.request

import cursor_gateway


def _server(monkeypatch, answer="ок"):
    monkeypatch.setattr(cursor_gateway, "GATEWAY_KEY", "test-key")
    monkeypatch.setattr(cursor_gateway, "_ask", lambda model, prompt, use_mcp=False: (0, answer))
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


def test_tool_call_is_returned_to_hermes(monkeypatch):
    answer = '{"tool_calls":[{"name":"yandex_recent","arguments":{"limit":5}}]}'
    server = _server(monkeypatch, answer=answer)
    try:
        status, content_type, raw = _post(server, {
            "model": "cursor-grok-4.6-high-fast",
            "messages": [{"role": "user", "content": "что в почте"}],
            "tools": [{"type": "function", "function": {
                "name": "yandex_recent",
                "description": "последние письма",
                "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
            }}],
        })
    finally:
        server.shutdown()
    body = json.loads(raw)
    message = body["choices"][0]["message"]
    assert status == 200
    assert content_type.startswith("application/json")
    assert body["choices"][0]["finish_reason"] == "tool_calls"
    assert message["tool_calls"][0]["function"]["name"] == "yandex_recent"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"limit": 5}


def test_tool_answer_uses_content_field(monkeypatch):
    server = _server(monkeypatch, answer='пояснение\n{"content":"писем нет"}')
    try:
        status, _, raw = _post(server, {
            "model": "m",
            "messages": [
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "yandex_recent", "arguments": "{}"},
                }]},
                {"role": "tool", "name": "yandex_recent", "tool_call_id": "call_1",
                 "content": "писем нет"},
            ],
            "tools": [{"type": "function", "function": {"name": "yandex_recent"}}],
        })
    finally:
        server.shutdown()
    assert status == 200
    assert json.loads(raw)["choices"][0]["message"]["content"] == "писем нет"


def test_mcp_run_keeps_shell_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(cursor_gateway, "WORKSPACE", str(tmp_path))
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class Proc:
            returncode = 0
            stdout = "ящик отвечает"
            stderr = ""

        return Proc()

    monkeypatch.setattr(cursor_gateway.subprocess, "run", fake_run)
    code, text = cursor_gateway._ask("cursor-grok-4.6-high-fast", "проверь почту", use_mcp=True)
    policy = json.loads((tmp_path / ".cursor" / "cli.json").read_text(encoding="utf-8"))
    servers = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert code == 0 and text == "ящик отвечает"
    assert "--mode" not in captured["argv"]
    assert "--approve-mcps" in captured["argv"]
    assert "--sandbox" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--sandbox") + 1] == "disabled"
    assert "--force" in captured["argv"]
    assert "--yolo" not in captured["argv"]
    assert "Shell(*)" in policy["permissions"]["deny"]
    assert "Write(**)" in policy["permissions"]["deny"]
    assert "Mcp(yandex:*)" in policy["permissions"]["allow"]
    assert "phone" not in servers["mcpServers"]
    assert servers["mcpServers"]["yandex"]["args"] == ["-m", "desk_mcp", "yandex"]
    assert "PASSWORD" not in json.dumps(servers)


def test_prompt_lists_tools_and_ask_mode_stays(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Proc()

    monkeypatch.setattr(cursor_gateway.subprocess, "run", fake_run)
    prompt = cursor_gateway._prompt(
        [{"role": "tool", "name": "calendar_events", "content": "встреч нет"}],
        [{"type": "function", "function": {"name": "calendar_events", "description": "расписание"}}],
    )
    code, text = cursor_gateway._ask("cursor-grok-4.6-high-fast", prompt)
    assert code == 0 and text == "ok"
    assert "calendar_events" in prompt
    assert "встреч нет" in prompt
    assert "MCP" in prompt
    mode = captured["argv"][captured["argv"].index("--mode") + 1]
    assert mode == "ask"
    assert "--force" not in captured["argv"]
    assert "--yolo" not in captured["argv"]


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
