#!/usr/bin/env python3
"""Журнал звонков из базы CallHistory.

iCloud синхронизирует журнал звонков iPhone на Mac — там он лежит в
`~/Library/Application Support/CallHistoryDB/CallHistory.storedata`,
обычным SQLite с таблицей `ZCALLRECORD`. Это тот же журнал, что в приложении
«Телефон»: обычные звонки, FaceTime и звонки сторонних приложений, которые
отдают их системе (WhatsApp, Telegram).

Ярлык iOS до этого журнала не дотягивается вообще — Apple не даёт. Поэтому
или так, или звонки приходится вносить руками, чего мы не хотим.
"""
import os
import shutil
import sqlite3
import tempfile

APPLE_EPOCH = 978307200

PROVIDERS = {
    "com.apple.telephonyutilities.callservicesd.selfcall": "phone",
    "com.apple.telephony": "phone",
    "com.apple.facetime": "facetime",
    "com.apple.facetime.audio": "facetime",
    "com.apple.facetime.video": "facetime",
    "net.whatsapp.whatsapp": "whatsapp",
    "ph.telegra.telegraph": "telegram",
    "org.whispersystems.signal": "signal",
}


def default_path():
    return os.path.expanduser(
        "~/Library/Application Support/CallHistoryDB/CallHistory.storedata")


def open_db(path, copy=True):
    path = path or default_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f"нет журнала звонков: {path}")
    if not copy:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True), None
    temp = tempfile.mkdtemp(prefix="phone-calls-")
    copied = os.path.join(temp, "CallHistory.storedata")
    shutil.copy2(path, copied)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.copy2(path + suffix, copied + suffix)
    return sqlite3.connect(copied), temp


def _text(value):
    """`ZADDRESS` — то строка, то BLOB с теми же байтами."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore").strip("\x00").strip()
    return str(value).strip()


def _app(provider, has_facetime):
    key = (provider or "").strip().lower()
    if key in PROVIDERS:
        return PROVIDERS[key]
    if has_facetime:
        return "facetime"
    if key and "." in key:
        return key.rsplit(".", 1)[-1]
    return "phone"


def read_calls(path=None, after=0.0, limit=5000):
    """Звонки позже указанного времени — в формате, который ждёт мост."""
    conn, temp = open_db(path)
    try:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(ZCALLRECORD)")}
        if not columns:
            return []
        # Набор колонок гуляет от версии к версии; спрашиваем только те,
        # что есть, иначе запрос падает целиком из-за одной отсутствующей.
        wanted = [c for c in ("Z_PK", "ZDATE", "ZDURATION", "ZORIGINATED",
                              "ZANSWERED", "ZADDRESS", "ZNAME", "ZSERVICE_PROVIDER",
                              "ZFACE_TIME_DATA", "ZUNIQUE_ID", "ZCALLTYPE")
                  if c in columns]
        after_apple = max(after - APPLE_EPOCH, 0)
        rows = conn.execute(
            f"SELECT {','.join(wanted)} FROM ZCALLRECORD"
            " WHERE ZDATE > ? ORDER BY ZDATE LIMIT ?", (after_apple, limit))
        out = []
        for row in rows:
            item = {key: row[key] for key in wanted}
            started = float(item.get("ZDATE") or 0) + APPLE_EPOCH
            duration = float(item.get("ZDURATION") or 0)
            outgoing = bool(item.get("ZORIGINATED"))
            answered = bool(item.get("ZANSWERED"))
            out.append({
                "external_id": _text(item.get("ZUNIQUE_ID")) or f"callhistory:{item['Z_PK']}",
                "direction": "outgoing" if outgoing else "incoming",
                "status": ("answered" if answered or (outgoing and duration > 0)
                           else ("declined" if outgoing else "missed")),
                "peer_number": _text(item.get("ZADDRESS")),
                "peer_name": _text(item.get("ZNAME")),
                "app": _app(item.get("ZSERVICE_PROVIDER"), item.get("ZFACE_TIME_DATA")),
                "started_at": started,
                "duration": duration,
            })
        return out
    finally:
        conn.close()
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
