#!/usr/bin/env python3
"""Хранилище моста: SQLite рядом с базой ядра, но своя.

Схема создаётся идемпотентно при старте. Всё, что приходит с телефона,
складывается сюда как есть; осмысление живёт в `insights.py`.

У каждой записи есть `external_id` — идентификатор события на телефоне.
Ярлык iOS не помнит, что он уже отправлял: при плохой связи он повторит
пакет целиком, и без ключа дедупликации один звонок превратился бы в пять.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid

from .config import config

_local = threading.local()

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS devices(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
        model TEXT, os_version TEXT, token_hash TEXT NOT NULL UNIQUE,
        created_at REAL, last_seen_at REAL, revoked INTEGER DEFAULT 0)""",

    """CREATE TABLE IF NOT EXISTS calls(
        id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, direction TEXT,
        status TEXT, peer_name TEXT, peer_number TEXT, app TEXT DEFAULT 'phone',
        started_at REAL, duration REAL DEFAULT 0, note TEXT,
        device_id TEXT, created_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_calls_started ON calls(started_at)",

    """CREATE TABLE IF NOT EXISTS messages(
        id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, app TEXT,
        direction TEXT, peer_name TEXT, peer_number TEXT, chars INTEGER DEFAULT 0,
        attachments INTEGER DEFAULT 0, preview TEXT, ts REAL,
        device_id TEXT, created_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts)",

    """CREATE TABLE IF NOT EXISTS samples(
        id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, metric TEXT NOT NULL,
        value REAL, unit TEXT, started_at REAL, ended_at REAL, source TEXT,
        device_id TEXT, created_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_samples_metric ON samples(metric, started_at)",

    """CREATE TABLE IF NOT EXISTS workouts(
        id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, kind TEXT,
        started_at REAL, ended_at REAL, duration REAL, energy REAL, distance REAL,
        avg_hr REAL, max_hr REAL, source TEXT, device_id TEXT, created_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_workouts_started ON workouts(started_at)",

    """CREATE TABLE IF NOT EXISTS device_state(
        device_id TEXT PRIMARY KEY, battery REAL, charging INTEGER, focus TEXT,
        place TEXT, network TEXT, extra TEXT, updated_at REAL)""",

    """CREATE TABLE IF NOT EXISTS sync_state(
        key TEXT PRIMARY KEY, value TEXT, updated_at REAL)""",

    """CREATE TABLE IF NOT EXISTS outbox(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT, target TEXT,
        status TEXT DEFAULT 'NEW', created_at REAL, taken_at REAL, done_at REAL,
        result TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, created_at)",
)


def new_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def path():
    """Окружение важнее собранной конфигурации: у тестов своя база."""
    return os.environ.get("PHONE_DB") or config.db_path


def connect():
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) != path():
        conn.close()
        conn = None
    if conn is None:
        conn = sqlite3.connect(path(), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        _local.conn = conn
        _local.path = path()
    return conn


def query(sql, params=()):
    return connect().execute(sql, params).fetchall()


def one(sql, params=()):
    return connect().execute(sql, params).fetchone()


def execute(sql, params=()):
    conn = connect()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor
    except Exception:
        conn.rollback()
        raise


def migrate():
    conn = connect()
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()


# --- устройства ----------------------------------------------------------
def hash_token(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def register_device(name, kind="iphone", model="", os_version=""):
    """Возвращает (устройство, токен). Токен показывается один раз."""
    token = secrets.token_urlsafe(32)
    device_id = new_id("dev-")
    now = time.time()
    execute("""INSERT INTO devices(id, name, kind, model, os_version, token_hash,
                created_at, last_seen_at, revoked) VALUES(?,?,?,?,?,?,?,NULL,0)""",
            (device_id, name, kind, model or "", os_version or "",
             hash_token(token), now))
    return device(device_id), token


def device(device_id):
    return _as_device(one("SELECT * FROM devices WHERE id=?", (device_id,)))


def device_by_token(token):
    if not token:
        return None
    return _as_device(one("SELECT * FROM devices WHERE token_hash=? AND revoked=0",
                          (hash_token(token),)))


def devices(include_revoked=False):
    sql = "SELECT * FROM devices"
    if not include_revoked:
        sql += " WHERE revoked=0"
    return [_as_device(row) for row in query(sql + " ORDER BY created_at")]


def revoke_device(device_id):
    cursor = execute("UPDATE devices SET revoked=1 WHERE id=?", (device_id,))
    return cursor.rowcount > 0


def touch_device(device_id, when=None):
    execute("UPDATE devices SET last_seen_at=? WHERE id=?",
            (when or time.time(), device_id))


def _as_device(row):
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "kind": row["kind"],
            "model": row["model"], "os_version": row["os_version"],
            "created_at": row["created_at"], "last_seen_at": row["last_seen_at"],
            "revoked": bool(row["revoked"])}


# --- события -------------------------------------------------------------
CALL_COLUMNS = ("id", "external_id", "direction", "status", "peer_name",
                "peer_number", "app", "started_at", "duration", "note",
                "device_id", "created_at")
MESSAGE_COLUMNS = ("id", "external_id", "app", "direction", "peer_name",
                   "peer_number", "chars", "attachments", "preview", "ts",
                   "device_id", "created_at")
SAMPLE_COLUMNS = ("id", "external_id", "metric", "value", "unit", "started_at",
                  "ended_at", "source", "device_id", "created_at")
WORKOUT_COLUMNS = ("id", "external_id", "kind", "started_at", "ended_at", "duration",
                   "energy", "distance", "avg_hr", "max_hr", "source", "device_id",
                   "created_at")


def call_row(call):
    return (new_id("cal-"), call["external_id"], call["direction"], call["status"],
            call.get("peer_name") or "", call.get("peer_number") or "",
            call.get("app") or "phone", call["started_at"], call.get("duration") or 0,
            call.get("note") or "", call.get("device_id"), time.time())


def message_row(message):
    return (new_id("msg-"), message["external_id"], message.get("app") or "imessage",
            message["direction"], message.get("peer_name") or "",
            message.get("peer_number") or "", message.get("chars") or 0,
            message.get("attachments") or 0, message.get("preview") or "",
            message["ts"], message.get("device_id"), time.time())


def sample_row(sample):
    return (new_id("smp-"), sample["external_id"], sample["metric"],
            sample.get("value"), sample.get("unit") or "", sample["started_at"],
            sample.get("ended_at") or sample["started_at"], sample.get("source") or "",
            sample.get("device_id"), time.time())


def workout_row(workout):
    return (new_id("wrk-"), workout["external_id"], workout.get("kind") or "",
            workout["started_at"], workout.get("ended_at"), workout.get("duration"),
            workout.get("energy"), workout.get("distance"), workout.get("avg_hr"),
            workout.get("max_hr"), workout.get("source") or "",
            workout.get("device_id"), time.time())


def save_many(table, columns, rows):
    """Сколько строк оказалось новыми. Остальные — повторы, их тихо отбросили.

    Только пачками: в выгрузке из «Здоровья» за пять лет миллионы замеров, и
    отдельная транзакция на каждый превращает импорт в часы.
    """
    rows = list(rows)
    if not rows:
        return 0
    conn = connect()
    before = conn.total_changes
    placeholders = ",".join("?" * len(columns))
    try:
        conn.executemany(f"INSERT OR IGNORE INTO {table}({','.join(columns)})"
                         f" VALUES({placeholders})", rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return conn.total_changes - before


def save_calls(calls):
    return save_many("calls", CALL_COLUMNS, [call_row(c) for c in calls])


def save_messages(messages):
    return save_many("messages", MESSAGE_COLUMNS, [message_row(m) for m in messages])


def save_samples(samples):
    return save_many("samples", SAMPLE_COLUMNS, [sample_row(s) for s in samples])


def save_workouts(workouts):
    return save_many("workouts", WORKOUT_COLUMNS, [workout_row(w) for w in workouts])


def save_call(call):
    return save_calls([call]) > 0


def save_message(message):
    return save_messages([message]) > 0


def save_sample(sample):
    return save_samples([sample]) > 0


def save_workout(workout):
    return save_workouts([workout]) > 0


def save_state(device_id, state):
    execute("""INSERT INTO device_state(device_id, battery, charging, focus, place,
                network, extra, updated_at) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(device_id) DO UPDATE SET battery=excluded.battery,
                charging=excluded.charging, focus=excluded.focus, place=excluded.place,
                network=excluded.network, extra=excluded.extra,
                updated_at=excluded.updated_at""",
            (device_id, state.get("battery"), int(bool(state.get("charging"))),
             state.get("focus") or "", state.get("place") or "",
             state.get("network") or "",
             json.dumps(state.get("extra") or {}, ensure_ascii=False), time.time()))


def states():
    out = []
    for row in query("SELECT * FROM device_state"):
        item = dict(row)
        item["charging"] = bool(item["charging"])
        try:
            item["extra"] = json.loads(item["extra"] or "{}")
        except ValueError:
            item["extra"] = {}
        out.append(item)
    return out


# --- чтение --------------------------------------------------------------
def calls(since=None, until=None, limit=200):
    return [dict(row) for row in query(
        "SELECT * FROM calls WHERE started_at >= ? AND started_at < ?"
        " ORDER BY started_at DESC LIMIT ?",
        (since or 0, until or time.time() + 86400, limit))]


def messages(since=None, until=None, limit=500):
    return [dict(row) for row in query(
        "SELECT * FROM messages WHERE ts >= ? AND ts < ? ORDER BY ts DESC LIMIT ?",
        (since or 0, until or time.time() + 86400, limit))]


def samples(metric=None, since=None, until=None, limit=5000):
    """`limit=None` — без ограничения: в дне с тренировкой пульс мерится
    сотнями раз, и обрезанная выборка молча занизила бы день."""
    sql = "SELECT * FROM samples WHERE started_at >= ? AND started_at < ?"
    params = [since or 0, until or time.time() + 86400]
    if metric:
        sql += " AND metric=?"
        params.append(metric)
    sql += " ORDER BY started_at"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(row) for row in query(sql, tuple(params))]


def metrics():
    return [row["metric"] for row in query(
        "SELECT metric, COUNT(*) c FROM samples GROUP BY metric ORDER BY c DESC")]


def workouts(since=None, until=None, limit=100):
    return [dict(row) for row in query(
        "SELECT * FROM workouts WHERE started_at >= ? AND started_at < ?"
        " ORDER BY started_at DESC LIMIT ?",
        (since or 0, until or time.time() + 86400, limit))]


def get_cursor(key, default=None):
    """Докуда дочитан внешний источник: chat.db, журнал звонков, выгрузка."""
    row = one("SELECT value FROM sync_state WHERE key=?", (key,))
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return default


def set_cursor(key, value):
    execute("""INSERT INTO sync_state(key, value, updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                updated_at=excluded.updated_at""",
            (key, json.dumps(value, ensure_ascii=False), time.time()))
    return value


def cursors():
    return {row["key"]: row["updated_at"]
            for row in query("SELECT key, updated_at FROM sync_state")}


def last_sync_at():
    row = one("SELECT MAX(last_seen_at) t FROM devices WHERE revoked=0")
    return row["t"] if row else None


# --- исходящие -----------------------------------------------------------
def push_outbox(kind, payload, target=""):
    item_id = new_id("out-")
    execute("""INSERT INTO outbox(id, kind, payload, target, status, created_at)
               VALUES(?,?,?,?,'NEW',?)""",
            (item_id, kind, json.dumps(payload or {}, ensure_ascii=False),
             target or "", time.time()))
    return outbox_item(item_id)


def take_outbox(limit=10, target=""):
    """Телефон забирает задания: он ходит сам, пуш-канала у нас нет."""
    sql = "SELECT * FROM outbox WHERE status='NEW'"
    params = []
    if target:
        sql += " AND (target='' OR target=?)"
        params.append(target)
    sql += " ORDER BY created_at LIMIT ?"
    params.append(limit)
    items = [_as_outbox(row) for row in query(sql, tuple(params))]
    now = time.time()
    for item in items:
        execute("UPDATE outbox SET status='TAKEN', taken_at=? WHERE id=?",
                (now, item["id"]))
        item["status"] = "TAKEN"
    return items


def ack_outbox(ids, results=None):
    results = results or {}
    now = time.time()
    done = 0
    for item_id in ids or []:
        cursor = execute(
            "UPDATE outbox SET status='DONE', done_at=?, result=? WHERE id=?"
            " AND status!='DONE'",
            (now, json.dumps(results.get(item_id, {}), ensure_ascii=False), item_id))
        done += cursor.rowcount
    return done


def outbox(status=None, limit=50):
    if status:
        rows = query("SELECT * FROM outbox WHERE status=? ORDER BY created_at DESC"
                     " LIMIT ?", (status, limit))
    else:
        rows = query("SELECT * FROM outbox ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_as_outbox(row) for row in rows]


def outbox_item(item_id):
    return _as_outbox(one("SELECT * FROM outbox WHERE id=?", (item_id,)))


def _as_outbox(row):
    if row is None:
        return None
    item = dict(row)
    for key in ("payload", "result"):
        try:
            item[key] = json.loads(item[key] or "{}")
        except ValueError:
            item[key] = {}
    return item


# --- уборка --------------------------------------------------------------
def prune(retention_days=None):
    """Чистка по сроку давности. Ноль — хранить всё.

    Ноль по умолчанию не от лени: в базу заезжает выгрузка «Здоровья» за все
    годы, и срок хранения в год молча съел бы её на первой же уборке.
    """
    days = retention_days if retention_days is not None else config.retention_days
    if not days or days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for table, column in (("calls", "started_at"), ("messages", "ts"),
                          ("samples", "started_at"), ("workouts", "started_at")):
        removed += execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,)).rowcount
    removed += execute("DELETE FROM outbox WHERE status='DONE' AND done_at < ?",
                       (time.time() - 7 * 86400,)).rowcount
    return removed
