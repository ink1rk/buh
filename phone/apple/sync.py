#!/usr/bin/env python3
"""Забрать данные из первоисточников Apple и положить в мост.

Один и тот же код работает в двух режимах:

* локально — пишет прямо в `phone.db`, когда агент и мост на одной машине;
* по HTTP — читает базы на Mac и отправляет пакет на `/v1/sync`, когда мост
  живёт на сервере, а переписка и журнал звонков — на маке владельца.

Курсор («до какой строки уже дочитали») хранится в мосте, поэтому повторный
запуск безвреден: уже виденное останется на месте, новое доедет.
"""
import os
import time

from .. import ingest, store
from . import backup, callhistory, chatdb
from .health_export import import_export

DEFAULT_DEVICE = "iPhone"


def ensure_device(name=None, kind="iphone"):
    name = name or DEFAULT_DEVICE
    for existing in store.devices():
        if existing["name"] == name:
            return existing
    device, _token = store.register_device(name, kind=kind)
    return device


def _touch(device_id, report):
    if device_id and report.get("new"):
        store.touch_device(device_id)
    return report


def pull_messages(path=None, device_id=None, cursor_key="chatdb.rowid"):
    path = path or chatdb.default_path()
    last = store.get_cursor(cursor_key, 0) or 0
    result = chatdb.read_messages(path, after_rowid=last)
    report = ingest.ingest_messages(result["items"], device_id)
    if result["last_rowid"] > last:
        store.set_cursor(cursor_key, result["last_rowid"])
    report["cursor"] = result["last_rowid"]
    return _touch(device_id, report)


def pull_calls(path=None, device_id=None, cursor_key="callhistory.ts"):
    path = path or callhistory.default_path()
    last = store.get_cursor(cursor_key, 0) or 0
    items = callhistory.read_calls(path, after=last)
    report = ingest.ingest_calls(items, device_id)
    if items:
        store.set_cursor(cursor_key, max(item["started_at"] for item in items))
    report["cursor"] = store.get_cursor(cursor_key, last)
    return _touch(device_id, report)


def pull_health(path, device_id=None, since=None, progress=None):
    report = import_export(path, device_id=device_id, since=since, progress=progress)
    store.set_cursor("health_export", {
        "path": os.path.basename(os.path.abspath(path)),
        "read": report.get("read", 0),
        "new": report.get("health", {}).get("new", 0)
               + report.get("workouts", {}).get("new", 0),
    })
    if device_id:
        store.touch_device(device_id)
    return report


def pull_mac(device_id=None, messages_path=None, calls_path=None):
    """Один проход по базам Mac: новое из переписки и журнала звонков."""
    device_id = device_id or ensure_device("Mac", kind="mac")["id"]
    result = {}
    if messages_path or os.path.exists(chatdb.default_path()):
        result["messages"] = pull_messages(messages_path, device_id)
    if calls_path or os.path.exists(callhistory.default_path()):
        result["calls"] = pull_calls(calls_path, device_id)
    if not result:
        raise FileNotFoundError(
            "на этой машине нет ни ~/Library/Messages/chat.db, "
            "ни журнала звонков. Включите «Сообщения в iCloud» "
            "или укажите пути явно.")
    result["accepted"] = sum(part.get("new", 0) for part in result.values())
    return result


def pull_backup(path=None, root=None, device_id=None):
    extracted = backup.extract(path, root=root)
    try:
        meta = extracted.meta
        device = None
        if device_id:
            device = store.device(device_id)
        if device is None:
            device = ensure_device(meta.get("name") or "iPhone", kind="iphone")
        result = {"device": device, "backup": meta}
        if "messages" in extracted.files:
            result["messages"] = pull_messages(
                extracted.files["messages"], device["id"],
                cursor_key=f"backup.{meta['udid']}.messages")
        if "calls" in extracted.files:
            result["calls"] = pull_calls(
                extracted.files["calls"], device["id"],
                cursor_key=f"backup.{meta['udid']}.calls")
        result["accepted"] = sum(part.get("new", 0) for part in result.values()
                                 if isinstance(part, dict))
        return result
    finally:
        extracted.close()


def package_new(messages_path=None, calls_path=None, after_rowid=0, after_call=0):
    """Прочитать новое и собрать пакет, который понимает `/v1/sync`.

    Курсор при этом не двигается: его двигает мост, когда пакет принят.
    Иначе оборванный POST потерял бы сообщения навсегда.
    """
    payload = {"messages": [], "calls": []}
    cursors = {"messages": after_rowid, "calls": after_call}
    if messages_path or os.path.exists(chatdb.default_path()):
        result = chatdb.read_messages(messages_path, after_rowid=after_rowid)
        payload["messages"] = [{k: v for k, v in item.items() if k != "rowid"}
                               for item in result["items"]]
        cursors["messages"] = result["last_rowid"]
    if calls_path or os.path.exists(callhistory.default_path()):
        items = callhistory.read_calls(calls_path, after=after_call)
        payload["calls"] = items
        if items:
            cursors["calls"] = max(item["started_at"] for item in items)
    return payload, cursors


def push_remote(url, token, messages_path=None, calls_path=None,
                after_rowid=0, after_call=0):
    """Отправить новое с Mac на мост. Нужен токен устройства, не MCP."""
    import httpx

    payload, cursors = package_new(messages_path, calls_path, after_rowid, after_call)
    if not payload["messages"] and not payload["calls"]:
        return {"accepted": 0, "cursors": cursors}
    response = httpx.post(
        url.rstrip("/") + "/v1/sync",
        json=payload,
        headers={"X-Device-Token": token, "Content-Type": "application/json"},
        timeout=60)
    response.raise_for_status()
    result = response.json()
    result["cursors"] = cursors
    return result


def watch(interval=30, url=None, token=None, messages_path=None, calls_path=None,
          device_id=None, once=False):
    """Смотреть базы и забирать новое. `once` — один проход, для тестов."""
    after_rowid = 0
    after_call = 0
    while True:
        try:
            if url:
                if not token:
                    raise RuntimeError("для --url нужен --token устройства")
                result = push_remote(url, token, messages_path, calls_path,
                                     after_rowid, after_call)
                cursors = result.get("cursors") or {}
                after_rowid = cursors.get("messages", after_rowid)
                after_call = cursors.get("calls", after_call)
            else:
                result = pull_mac(device_id, messages_path, calls_path)
            accepted = result.get("accepted", 0)
            if accepted:
                print(f"{time.strftime('%H:%M:%S')} +{accepted}", flush=True)
        except FileNotFoundError:
            raise
        except Exception as exc:                    # noqa: BLE001
            print(f"{time.strftime('%H:%M:%S')} ошибка: {exc}", flush=True)
        if once:
            return result
        time.sleep(interval)
