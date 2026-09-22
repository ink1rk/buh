"""Протокол MCP: обе эпохи, проверка заголовков и сами инструменты."""
import io
import json

import pytest
from conftest import at

from phone import ingest, mcp, tools


def ask(method, params=None, version=mcp.LATEST, message_id=1, headers=None,
        transport="http", with_meta=True):
    params = dict(params or {})
    if with_meta:
        params["_meta"] = mcp.client_meta(version)
    body = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}
    if headers is None and transport == "http":
        headers = mcp.request_headers(method, version,
                                      params.get("name") or params.get("uri"))
    return tools.server.handle(body, headers=headers, transport=transport)


def result(reply):
    assert reply.status == 200, reply.body
    assert "error" not in reply.body, reply.body
    return reply.body["result"]


def error(reply):
    return reply.body["error"]


# --- современная эпоха ---------------------------------------------------
def test_the_server_tells_which_versions_it_speaks():
    payload = result(ask("server/discover"))

    assert mcp.LATEST in payload["supportedVersions"]
    assert payload["capabilities"]["tools"] is not None
    assert "iPhone" in payload["instructions"]


def test_every_answer_names_the_server():
    """В протоколе без сессий клиент узнаёт сервер только из ответа."""
    payload = result(ask("tools/list"))

    assert payload["_meta"][mcp.META_SERVER]["name"] == "jarvis-phone"
    assert payload["resultType"] == "complete"


def test_a_tool_list_can_be_cached():
    payload = result(ask("tools/list"))

    assert payload["ttlMs"] > 0
    assert {tool["name"] for tool in payload["tools"]} >= {
        "phone_today", "phone_attention", "phone_health", "phone_calls", "phone_push"}


def test_a_tool_returns_text_and_structure(device):
    ingest.ingest_health([{"metric": "steps", "value": 8200, "start": at(0, 10)}],
                         device[0]["id"])

    payload = result(ask("tools/call", {"name": "phone_today", "arguments": {}}))

    assert payload["isError"] is False
    assert "8200 шагов" in payload["content"][0]["text"]
    assert payload["structuredContent"]["health"]["steps"]["value"] == 8200


def test_a_tool_complaint_reaches_the_model_not_the_transport():
    """Ошибку инструмента модель должна увидеть и исправиться, а не упасть."""
    payload = result(ask("tools/call", {"name": "phone_health",
                                        "arguments": {"metric": "мурлыканье"}}))

    assert payload["isError"] is True
    assert "данных нет" in payload["content"][0]["text"]


def test_an_unknown_tool_is_a_protocol_error():
    reply = ask("tools/call", {"name": "phone_fly", "arguments": {}})

    assert error(reply)["code"] == mcp.INVALID_PARAMS


def test_resources_are_readable():
    listed = result(ask("resources/list"))
    assert "phone://today" in {item["uri"] for item in listed["resources"]}

    payload = result(ask("resources/read", {"uri": "phone://today"}))
    body = json.loads(payload["contents"][0]["text"])
    assert "health" in body and "attention" in body


# --- заголовки, по которым маршрутизирует шлюз ---------------------------
def test_a_gateway_can_route_by_headers():
    """Ради этого и заголовки: метод и имя видны, тело читать не нужно."""
    headers = mcp.request_headers("tools/call", name="phone_attention")

    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "phone_attention"
    assert result(ask("tools/call", {"name": "phone_attention", "arguments": {}},
                      headers=headers))["isError"] is False


def test_a_name_that_is_not_ascii_travels_encoded():
    encoded = mcp._header_value("сон")
    assert encoded.startswith("=?base64?")
    assert mcp.decode_header(encoded) == "сон"


def test_headers_and_body_must_agree():
    """Иначе шлюз пускает один запрос, а сервер выполняет другой."""
    headers = mcp.request_headers("tools/call", name="phone_attention")
    reply = ask("tools/call", {"name": "phone_push", "arguments": {"text": "привет"}},
                headers=headers)

    assert reply.status == 400
    assert error(reply)["code"] == mcp.HEADER_MISMATCH


def test_a_missing_method_header_is_refused():
    reply = ask("tools/list", headers={"MCP-Protocol-Version": mcp.LATEST})

    assert reply.status == 400 and error(reply)["code"] == mcp.HEADER_MISMATCH


def test_the_version_in_the_header_must_match_the_body():
    headers = mcp.request_headers("tools/list", version="2025-11-25")
    reply = ask("tools/list", version=mcp.LATEST, headers=headers)

    assert reply.status == 400 and error(reply)["code"] == mcp.HEADER_MISMATCH


def test_an_unknown_version_gets_the_list_of_known_ones():
    reply = ask("tools/list", version="1999-01-01")

    assert reply.status == 400
    assert error(reply)["code"] == mcp.UNSUPPORTED_PROTOCOL_VERSION
    assert error(reply)["data"]["supported"] == list(mcp.SUPPORTED)


def test_stdio_needs_no_headers():
    payload = result(ask("tools/list", transport="stdio", headers={}))
    assert payload["tools"]


# --- клиенты старой эпохи ------------------------------------------------
def test_an_old_client_still_shakes_hands():
    """Большинство готовых клиентов пока умеют только `initialize`."""
    reply = tools.server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "cursor", "version": "1.0"}}},
        transport="http")

    payload = result(reply)
    assert payload["protocolVersion"] == "2025-06-18"
    assert payload["serverInfo"]["name"] == "jarvis-phone"


def test_an_old_client_calls_tools_without_headers():
    reply = tools.server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "phone_attention", "arguments": {},
                    "_meta": {mcp.META_VERSION: "2025-06-18"}}},
        transport="http")

    payload = result(reply)
    assert "resultType" not in payload      # поле появилось только в 2026-07-28


def test_an_unknown_initialize_version_falls_back_to_a_known_one():
    reply = tools.server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
        transport="http")

    assert result(reply)["protocolVersion"] in mcp.SUPPORTED


def test_the_handshake_is_gone_in_the_new_version():
    reply = ask("initialize", {"protocolVersion": mcp.LATEST})

    assert reply.status == 404
    assert error(reply)["code"] == mcp.METHOD_NOT_FOUND


# --- мелочи протокола ----------------------------------------------------
def test_an_unknown_method_is_a_404():
    reply = ask("prompts/list")

    assert reply.status == 404 and error(reply)["code"] == mcp.METHOD_NOT_FOUND


def test_a_notification_gets_no_answer():
    reply = tools.server.handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}, transport="http")

    assert reply.status == 202 and reply.body is None


def test_ping_is_empty_but_polite():
    assert result(ask("ping"))["resultType"] == "complete"


def test_something_that_is_not_json_rpc_is_refused():
    reply = tools.server.handle({"hello": "world"}, transport="http")

    assert reply.status == 400 and error(reply)["code"] == mcp.INVALID_REQUEST


# --- stdio ---------------------------------------------------------------
def test_the_same_server_answers_over_stdio():
    """Клиенты вроде Cursor запускают сервер сами и говорят через трубу."""
    incoming = io.StringIO(json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/list",
        "params": {"_meta": mcp.client_meta()}}) + "\n")
    outgoing = io.StringIO()

    mcp.serve_stdio(tools.server, stdin=incoming, stdout=outgoing)

    answer = json.loads(outgoing.getvalue().strip())
    assert answer["id"] == 7 and answer["result"]["tools"]


def test_broken_json_over_stdio_does_not_kill_the_server():
    incoming = io.StringIO("{ не json\n" + json.dumps({
        "jsonrpc": "2.0", "id": 8, "method": "ping",
        "params": {"_meta": mcp.client_meta()}}) + "\n")
    outgoing = io.StringIO()

    mcp.serve_stdio(tools.server, stdin=incoming, stdout=outgoing)

    first, second = [json.loads(line) for line in
                     outgoing.getvalue().strip().splitlines()]
    assert first["error"]["code"] == mcp.PARSE_ERROR
    assert second["id"] == 8


# --- запись --------------------------------------------------------------
def test_a_task_for_the_phone_waits_in_the_queue(device):
    from phone import store

    payload = result(ask("tools/call", {
        "name": "phone_push",
        "arguments": {"text": "Позвонить Саше", "kind": "reminder"}}))

    assert payload["isError"] is False
    assert store.outbox("NEW")[0]["payload"]["text"] == "Позвонить Саше"


def test_a_task_for_an_unknown_device_is_refused():
    payload = result(ask("tools/call", {
        "name": "phone_push",
        "arguments": {"text": "Привет", "target": "dev-нет"}}))

    assert payload["isError"] is True


@pytest.mark.parametrize("tool_name", ["phone_today", "phone_attention",
                                       "phone_calls", "phone_messages",
                                       "phone_workouts", "phone_devices"])
def test_every_read_tool_survives_an_empty_bridge(tool_name):
    """Первый запуск: базы почти нет, а модель уже спрашивает."""
    payload = result(ask("tools/call", {"name": tool_name, "arguments": {}}))

    assert payload["content"][0]["text"]
