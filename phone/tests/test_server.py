"""HTTP-лицо моста: приём от ярлыков, выдача по MCP и кто куда допущен."""
import dataclasses

import pytest
from conftest import at
from fastapi.testclient import TestClient

from phone import mcp, store
from phone.config import config


@pytest.fixture
def client(monkeypatch):
    from phone import server
    monkeypatch.setattr(server, "config", dataclasses.replace(
        config, enroll_token="enroll-secret", mcp_token="mcp-secret"))
    return TestClient(server.create_app(testing=True))


@pytest.fixture
def phone(client):
    answer = client.post("/v1/devices/register",
                         headers={"Authorization": "Bearer enroll-secret"},
                         json={"name": "iPhone", "kind": "iphone"})
    body = answer.json()
    return client, body["token"], body["device"]["id"]


def headers(token):
    return {"X-Device-Token": token}


# --- постановка на учёт --------------------------------------------------
def test_a_stranger_cannot_enrol_a_device(client):
    answer = client.post("/v1/devices/register", json={"name": "чужой телефон"})

    assert answer.status_code == 401


def test_coming_from_the_local_address_grants_nothing(monkeypatch):
    """Мост стоит за прокси, и оттуда все запросы выглядят местными.

    Сервис слушает только loopback, поэтому запрос с улицы приходит к нему с
    адресом 127.0.0.1. Поблажка «со своей машины можно без токена» отдала бы
    незнакомцу и здоровье, и геопозицию, и право ставить устройства на учёт.
    """
    from phone import server
    monkeypatch.setattr(server, "config", dataclasses.replace(
        config, enroll_token="enroll-secret", mcp_token="mcp-secret"))
    local = TestClient(server.create_app(testing=True),
                       client=("127.0.0.1", 50000))

    assert local.post("/v1/devices/register",
                      json={"name": "чужой телефон"}).status_code == 401
    assert local.get("/v1/devices").status_code == 401
    assert local.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/list"}).status_code == 401


def test_an_unset_token_closes_the_door_rather_than_opening_it(monkeypatch):
    """Забытая настройка не должна превращаться в открытый вход."""
    from phone import server
    monkeypatch.setattr(server, "config", dataclasses.replace(
        config, enroll_token="", mcp_token=""))
    open_bridge = TestClient(server.create_app(testing=True),
                             client=("127.0.0.1", 50000))

    assert open_bridge.post("/v1/devices/register",
                            json={"name": "телефон"}).status_code == 401
    assert open_bridge.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                          "method": "tools/list"}).status_code == 401


def test_the_token_is_shown_once_and_then_only_its_hash(phone):
    client, token, device_id = phone

    assert len(token) > 20
    listed = client.get("/v1/devices",
                        headers={"Authorization": "Bearer mcp-secret"}).json()
    assert listed["devices"][0]["id"] == device_id
    assert "token" not in listed["devices"][0]


def test_a_revoked_device_stops_being_heard(phone):
    client, token, device_id = phone
    client.post(f"/v1/devices/{device_id}/revoke",
                headers={"Authorization": "Bearer enroll-secret"})

    assert client.post("/v1/sync", headers=headers(token),
                       json={"calls": []}).status_code == 401


# --- приём ---------------------------------------------------------------
def test_one_request_carries_the_whole_day(phone):
    client, token, _ = phone

    answer = client.post("/v1/sync", headers=headers(token), json={
        "calls": [{"direction": "incoming", "status": "missed", "peer_name": "Саша",
                   "peer_number": "+79991234567", "started_at": at(0, 9)}],
        "health": [{"metric": "steps", "value": 8200, "start": at(0, 10)}],
        "state": {"battery": 0.64, "focus": "Работа"},
    }).json()

    assert answer["calls"]["new"] == 1 and answer["health"]["new"] == 1
    assert answer["accepted"] == 2
    assert store.states()[0]["focus"] == "Работа"


def test_a_repeated_request_changes_nothing(phone):
    client, token, _ = phone
    payload = {"calls": [{"external_id": "c-1", "direction": "incoming",
                          "status": "missed", "started_at": at(0, 9)}]}

    client.post("/v1/sync", headers=headers(token), json=payload)
    again = client.post("/v1/sync", headers=headers(token), json=payload).json()

    assert again["calls"]["duplicates"] == 1
    assert len(store.calls()) == 1


def test_an_unknown_token_is_not_served(client):
    answer = client.post("/v1/sync", headers=headers("made-up-token"), json={})

    assert answer.status_code == 401


def test_narrow_endpoints_exist_for_simple_shortcuts(phone):
    """Ярлык «записать звонок» не должен собирать пакет целиком."""
    client, token, _ = phone

    answer = client.post("/v1/calls", headers=headers(token), json={
        "calls": [{"direction": "outgoing", "status": "answered",
                   "peer_name": "Аня", "started_at": at(0, 12), "duration": 60}]})

    assert answer.json()["new"] == 1


# --- задания телефону ----------------------------------------------------
def test_the_phone_takes_its_tasks_with_the_same_request(phone):
    """Одна синхронизация в обе стороны: телефону некогда ходить дважды."""
    client, token, _ = phone
    store.push_outbox("notify", {"text": "Пора выходить"})

    answer = client.post("/v1/sync", headers=headers(token), json={}).json()

    assert answer["outbox"][0]["payload"]["text"] == "Пора выходить"


def test_a_taken_task_is_not_handed_out_twice(phone):
    client, token, _ = phone
    store.push_outbox("notify", {"text": "Пора выходить"})

    client.get("/v1/outbox", headers=headers(token))
    second = client.get("/v1/outbox", headers=headers(token)).json()

    assert second["items"] == []


def test_the_phone_reports_what_it_did(phone):
    client, token, _ = phone
    item = store.push_outbox("notify", {"text": "Пора выходить"})
    client.get("/v1/outbox", headers=headers(token))

    answer = client.post("/v1/outbox/ack", headers=headers(token),
                         json={"ids": [item["id"]], "results": {item["id"]: {"shown": True}}})

    assert answer.json()["done"] == 1
    assert store.outbox_item(item["id"])["status"] == "DONE"


# --- MCP поверх HTTP -----------------------------------------------------
def mcp_call(client, method, params=None, token="mcp-secret", origin=None):
    params = dict(params or {})
    params["_meta"] = mcp.client_meta()
    request_headers = mcp.request_headers(method, name=params.get("name"))
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if origin:
        request_headers["Origin"] = origin
    return client.post("/mcp", headers=request_headers, json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def test_the_model_reaches_the_tools_over_http(phone):
    client, token, _ = phone
    client.post("/v1/sync", headers=headers(token), json={
        "health": [{"metric": "steps", "value": 9000, "start": at(0, 10)}]})

    answer = mcp_call(client, "tools/call",
                      {"name": "phone_today", "arguments": {}})

    assert answer.status_code == 200
    assert "9000 шагов" in answer.json()["result"]["content"][0]["text"]


def test_without_a_token_the_health_of_the_owner_is_not_public(client):
    assert mcp_call(client, "tools/list", token=None).status_code == 401


def test_a_web_page_cannot_reach_the_bridge(client):
    """Защита от DNS rebinding: браузер с чужой страницы — не клиент моста."""
    answer = mcp_call(client, "tools/list", origin="https://example.com")

    assert answer.status_code == 403


def test_there_is_no_event_stream_to_open(client):
    """Сессии и GET-поток протокол 2026-07-28 отменил."""
    assert client.get("/mcp").status_code == 405


def test_a_broken_body_is_a_parse_error(client):
    answer = client.post("/mcp", content="{не json",
                         headers={"Authorization": "Bearer mcp-secret",
                                  "Content-Type": "application/json"})

    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == mcp.PARSE_ERROR


# --- состояние -----------------------------------------------------------
def test_health_shows_the_bridge_is_alive(phone):
    client, token, _ = phone
    client.post("/v1/sync", headers=headers(token), json={})

    body = client.get("/health").json()

    assert body["status"] == "ok" and body["devices"] == 1


def test_health_admits_when_the_phone_went_quiet(phone):
    import time
    client, token, device_id = phone
    store.touch_device(device_id, when=time.time() - 24 * 3600)

    assert client.get("/health").json()["status"] == "degraded"
