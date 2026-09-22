"""Звонки и переписка из баз Apple и из резервной копии iPhone."""
import os
import plistlib
import shutil
import sqlite3
import time

import pytest

from phone import ingest, store
from phone.apple import backup, callhistory, chatdb, sync

APPLE_EPOCH = 978307200


def _apple(ts):
    return ts - APPLE_EPOCH


def _chat_db(path, rows):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, display_name TEXT, room_name TEXT);
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY, guid TEXT, date REAL, is_from_me INTEGER,
            service TEXT, cache_has_attachments INTEGER, text TEXT,
            attributedBody BLOB, handle_id INTEGER);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
    """)
    conn.execute("INSERT INTO handle(ROWID, id) VALUES (1, '+79991234567')")
    conn.execute("INSERT INTO handle(ROWID, id) VALUES (2, '+79990000000')")
    conn.execute("INSERT INTO chat(ROWID, display_name, room_name) VALUES (1, 'Саша', NULL)")
    conn.execute("INSERT INTO chat(ROWID, display_name, room_name) VALUES (2, 'семья', 'chat123')")
    for row in rows:
        conn.execute(
            """INSERT INTO message(ROWID, guid, date, is_from_me, service,
               cache_has_attachments, text, attributedBody, handle_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (row["rowid"], row.get("guid") or f"g-{row['rowid']}",
             _apple(row["ts"]), int(row.get("from_me", 0)),
             row.get("service", "iMessage"), int(row.get("attachments", 0)),
             row.get("text"), row.get("body"), row.get("handle", 1)))
        conn.execute("INSERT INTO chat_message_join VALUES (?, ?)",
                     (row.get("chat", 1), row["rowid"]))
    conn.commit()
    conn.close()


def _calls_db(path, rows, columns=None):
    columns = columns or (
        "Z_PK INTEGER PRIMARY KEY, ZDATE REAL, ZDURATION REAL, ZORIGINATED INTEGER, "
        "ZANSWERED INTEGER, ZADDRESS TEXT, ZNAME TEXT, ZSERVICE_PROVIDER TEXT, "
        "ZFACE_TIME_DATA BLOB, ZUNIQUE_ID TEXT")
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE ZCALLRECORD ({columns})")
    for row in rows:
        conn.execute(
            """INSERT INTO ZCALLRECORD(Z_PK, ZDATE, ZDURATION, ZORIGINATED, ZANSWERED,
               ZADDRESS, ZNAME, ZSERVICE_PROVIDER, ZUNIQUE_ID)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (row["pk"], _apple(row["ts"]), row.get("duration", 0),
             int(row.get("out", 0)), int(row.get("answered", 0)),
             row.get("number", "+79991234567"), row.get("name", "Саша"),
             row.get("provider", "com.apple.telephony"),
             row.get("uid") or f"call-{row['pk']}"))
    conn.commit()
    conn.close()


def test_messages_are_read_without_keeping_the_text(tmp_path):
    path = str(tmp_path / "chat.db")
    now = time.time()
    _chat_db(path, [{"rowid": 10, "ts": now - 3600, "text": "секреты фирмы"}])

    result = chatdb.read_messages(path)
    [message] = result["items"]
    assert message["direction"] == "incoming"
    assert message["peer_number"] == "+79991234567"
    assert message["chars"] == len("секреты фирмы")
    assert all("секреты" not in str(value) for value in message.values())
    assert result["last_rowid"] == 10


def test_group_chats_are_skipped_but_the_cursor_moves(tmp_path):
    path = str(tmp_path / "chat.db")
    now = time.time()
    _chat_db(path, [
        {"rowid": 1, "ts": now - 100, "text": "всем привет", "chat": 2, "handle": 2},
        {"rowid": 2, "ts": now - 50, "text": "личное", "chat": 1},
    ])

    result = chatdb.read_messages(path)
    assert [m["chars"] for m in result["items"]] == [len("личное")]
    assert result["last_rowid"] == 2


def test_attributed_body_gives_length_without_the_string(tmp_path):
    """С Ventura текст сидит в архиве NSAttributedString, не в колонке text."""
    text = "привет"
    raw = text.encode()
    # В архиве длина — число байт UTF-8, не число букв: иначе от «привет»
    # осталось бы три символа.
    blob = b"xxxxNSString?????" + bytes([len(raw)]) + raw
    path = str(tmp_path / "chat.db")
    _chat_db(path, [{"rowid": 1, "ts": time.time(), "text": None, "body": blob}])

    [message] = chatdb.read_messages(path)["items"]
    assert message["chars"] == len(text)


def test_a_missed_call_and_a_whatsapp_call_are_both_kept(tmp_path):
    path = str(tmp_path / "CallHistory.storedata")
    now = time.time()
    _calls_db(path, [
        {"pk": 1, "ts": now - 7200, "duration": 0, "out": 0, "answered": 0},
        {"pk": 2, "ts": now - 3600, "duration": 90, "out": 1, "answered": 1,
         "provider": "net.whatsapp.WhatsApp", "name": "Аня",
         "number": "+79990000000"},
    ])

    rows = callhistory.read_calls(path)
    assert rows[0]["status"] == "missed" and rows[0]["direction"] == "incoming"
    assert rows[1]["app"] == "whatsapp"
    assert rows[1]["status"] == "answered"


def test_missing_columns_do_not_kill_an_old_call_db(tmp_path):
    path = str(tmp_path / "CallHistory.storedata")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ZCALLRECORD (Z_PK INTEGER, ZDATE REAL, ZDURATION REAL, "
                 "ZORIGINATED INTEGER, ZANSWERED INTEGER, ZADDRESS TEXT)")
    conn.execute("INSERT INTO ZCALLRECORD VALUES (1, ?, 0, 0, 0, '+79991112233')",
                 (_apple(time.time() - 100),))
    conn.commit()
    conn.close()

    [row] = callhistory.read_calls(path)
    assert row["status"] == "missed"
    assert row["peer_number"] == "+79991112233"


def test_mac_sync_is_incremental(tmp_path):
    path = str(tmp_path / "chat.db")
    now = time.time()
    _chat_db(path, [{"rowid": 1, "ts": now - 100, "text": "раз"}])
    device, _ = store.register_device("Mac", kind="mac")

    first = sync.pull_messages(path, device["id"])
    assert first["new"] == 1
    conn = sqlite3.connect(path)
    conn.execute(
        """INSERT INTO message(ROWID, guid, date, is_from_me, service,
           cache_has_attachments, text, attributedBody, handle_id)
           VALUES (2, 'g-2', ?, 0, 'iMessage', 0, 'два', NULL, 1)""",
        (_apple(now - 10),))
    conn.execute("INSERT INTO chat_message_join VALUES (1, 2)")
    conn.commit()
    conn.close()
    again = sync.pull_messages(path, device["id"])
    assert again["new"] == 1
    assert len(store.messages()) == 2


def _backup(root, encrypted=False, with_files=True):
    folder = os.path.join(root, "UDID123")
    os.makedirs(folder)
    with open(os.path.join(folder, "Info.plist"), "wb") as fh:
        plistlib.dump({"Device Name": "iPhone Кирилла", "Product Type": "iPhone17,1",
                       "Product Version": "26.0"}, fh)
    with open(os.path.join(folder, "Manifest.plist"), "wb") as fh:
        plistlib.dump({"IsEncrypted": encrypted}, fh)
    with open(os.path.join(folder, "Status.plist"), "wb") as fh:
        plistlib.dump({"SnapshotState": "finished"}, fh)

    conn = sqlite3.connect(os.path.join(folder, "Manifest.db"))
    conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, "
                 "flags INTEGER, file BLOB)")
    if with_files:
        sms = os.path.join(root, "sms.db")
        calls = os.path.join(root, "calls.db")
        _chat_db(sms, [{"rowid": 7, "ts": time.time() - 60, "text": "из копии"}])
        _calls_db(calls, [{"pk": 3, "ts": time.time() - 120, "duration": 0}])
        sources = {
            ("aa" * 20, "HomeDomain", "Library/SMS/sms.db"): sms,
            ("bb" * 20, "HomeDomain", "Library/CallHistoryDB/CallHistory.storedata"): calls,
        }
        for (file_id, domain, relative), src in sources.items():
            conn.execute("INSERT INTO Files VALUES (?,?,?,1,X'')",
                         (file_id, domain, relative))
            dest_dir = os.path.join(folder, file_id[:2])
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(dest_dir, file_id))
    conn.commit()
    conn.close()
    return folder


def test_an_iphone_backup_gives_calls_and_messages(tmp_path):
    folder = _backup(str(tmp_path))
    result = sync.pull_backup(folder)

    assert result["accepted"] == 2
    assert store.messages()[0]["chars"] == len("из копии")
    assert store.calls()[0]["status"] == "missed"
    assert result["device"]["name"] == "iPhone Кирилла"


def test_an_encrypted_backup_is_refused(tmp_path):
    folder = _backup(str(tmp_path), encrypted=True)
    with pytest.raises(backup.EncryptedBackup):
        backup.extract(folder)


def test_no_backup_explains_what_to_do(tmp_path):
    with pytest.raises(backup.NoBackup):
        backup.latest(str(tmp_path / "empty"))


def test_package_new_does_not_move_the_cursor(tmp_path):
    """Оборванный POST не должен потерять сообщения: курсор двигает мост."""
    path = str(tmp_path / "chat.db")
    _chat_db(path, [{"rowid": 4, "ts": time.time(), "text": "ещё"}])
    payload, cursors = sync.package_new(messages_path=path, after_rowid=0)
    assert payload["messages"][0]["chars"] == len("ещё")
    assert cursors["messages"] == 4
    assert store.get_cursor("chatdb.rowid") is None


def test_health_auto_export_unpacks_sleep_stages(device):
    ingest.ingest_batch({"data": {"metrics": [{
        "name": "sleep_analysis", "units": "hr",
        "data": [{"date": "2026-09-21 00:00:00 +0300",
                  "sleepStart": "2026-09-20 23:30:00 +0300",
                  "sleepEnd": "2026-09-21 07:00:00 +0300",
                  "asleep": 6.5, "deep": 1.4, "rem": 1.6, "inBed": 7.5}],
    }]}}, device[0]["id"])

    names = {s["metric"]: s["value"] for s in store.samples(limit=None)}
    assert names["sleep"] == 6.5
    assert names["sleep_deep"] == 1.4
    assert names["sleep_rem"] == 1.6
    assert names["sleep_in_bed"] == 7.5


def test_health_auto_export_workout_v2(device):
    ingest.ingest_workouts([{
        "id": "w1", "name": "Running",
        "start": "2026-09-21 07:00:00 +0300",
        "end": "2026-09-21 07:45:00 +0300",
        "duration": 2700,
        "activeEnergy": {"qty": 410, "units": "kcal"},
        "distance": {"qty": 6.2, "units": "km"},
        "avgHeartRate": {"qty": 151, "units": "bpm"},
    }], device[0]["id"])

    [workout] = store.workouts(since=0)
    assert workout["duration"] == pytest.approx(45)
    assert workout["energy"] == 410
    assert workout["avg_hr"] == 151
