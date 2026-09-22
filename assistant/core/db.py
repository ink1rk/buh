#!/usr/bin/env python3
"""SQLite access and schema for the core.

One database for the whole assistant (the one that already existed). Tables are
created idempotently; older installations keep their `messages`/`facts` tables
untouched so nothing that already works breaks.
"""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import config

_local = threading.local()

SCHEMA = (
    # --- Phase 1: core plumbing -------------------------------------------
    """CREATE TABLE IF NOT EXISTS events(
        id TEXT PRIMARY KEY, type TEXT NOT NULL, source TEXT, payload TEXT,
        correlation_id TEXT, causation_id TEXT, ts REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)",
    "CREATE INDEX IF NOT EXISTS idx_events_corr ON events(correlation_id)",

    """CREATE TABLE IF NOT EXISTS actions(
        id TEXT PRIMARY KEY, type TEXT NOT NULL, source TEXT,
        parameters TEXT, risk_level TEXT, status TEXT NOT NULL,
        requires_confirmation INTEGER DEFAULT 0, requested_by TEXT,
        idempotency_key TEXT UNIQUE, correlation_id TEXT,
        created_at REAL, approved_at REAL, executed_at REAL, expires_at REAL,
        attempts INTEGER DEFAULT 0, result TEXT, error TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)",
    "CREATE INDEX IF NOT EXISTS idx_actions_created ON actions(created_at)",

    """CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
        correlation_id TEXT, actor TEXT, event TEXT NOT NULL,
        entity_type TEXT, entity_id TEXT, details TEXT, level TEXT DEFAULT 'info')""",
    "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)",
    "CREATE INDEX IF NOT EXISTS idx_audit_corr ON audit_log(correlation_id)",

    """CREATE TABLE IF NOT EXISTS notifications(
        id TEXT PRIMARY KEY, type TEXT, title TEXT, body TEXT, severity TEXT,
        channel TEXT, recipient TEXT, status TEXT, metadata TEXT,
        correlation_id TEXT, created_at REAL, sent_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)",

    """CREATE TABLE IF NOT EXISTS integrations(
        name TEXT PRIMARY KEY, type TEXT, status TEXT, detail TEXT,
        checked_at REAL, enabled INTEGER DEFAULT 1)""",

    "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)",

    # --- Phase 2: people, conversations, memory ---------------------------
    """CREATE TABLE IF NOT EXISTS contacts(
        id TEXT PRIMARY KEY, display_name TEXT NOT NULL, first_name TEXT,
        last_name TEXT, aliases TEXT, telegram_ids TEXT, emails TEXT, phones TEXT,
        notes TEXT, importance REAL DEFAULT 0.5, relationship_type TEXT DEFAULT 'UNKNOWN',
        relationship_source TEXT DEFAULT 'LLM_INFERENCE',
        communication_style TEXT, is_owner INTEGER DEFAULT 0,
        created_at REAL, updated_at REAL, last_interaction_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(display_name)",

    """CREATE TABLE IF NOT EXISTS conversations(
        id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_id TEXT,
        contact_id TEXT, title TEXT, status TEXT DEFAULT 'ACTIVE', summary TEXT,
        summary_updated_at REAL, created_at REAL, updated_at REAL,
        last_message_at REAL,
        UNIQUE(platform, external_id))""",

    """CREATE TABLE IF NOT EXISTS conv_messages(
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, external_id TEXT,
        sender_id TEXT, sender_type TEXT, text TEXT, message_type TEXT DEFAULT 'TEXT',
        transcription TEXT, ts REAL, reply_to TEXT, metadata TEXT,
        UNIQUE(conversation_id, external_id))""",
    "CREATE INDEX IF NOT EXISTS idx_convmsg_conv ON conv_messages(conversation_id, ts)",

    """CREATE TABLE IF NOT EXISTS memories(
        id TEXT PRIMARY KEY, type TEXT NOT NULL, content TEXT NOT NULL,
        source TEXT NOT NULL, source_id TEXT, entity_id TEXT, scope TEXT DEFAULT 'GLOBAL',
        confidence REAL DEFAULT 0.5, importance REAL DEFAULT 0.5,
        status TEXT DEFAULT 'ACTIVE', supersedes_id TEXT, conflict_with TEXT,
        tokens TEXT, created_at REAL, updated_at REAL, expires_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_memories_entity ON memories(entity_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type, status)",

    """CREATE TABLE IF NOT EXISTS episodes(
        id TEXT PRIMARY KEY, conversation_id TEXT, contact_id TEXT, title TEXT,
        summary TEXT, decisions TEXT, commitments TEXT, entities TEXT,
        started_at REAL, ended_at REAL, created_at REAL, updated_at REAL)""",

    """CREATE TABLE IF NOT EXISTS commitments(
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, counterparty_id TEXT,
        direction TEXT NOT NULL, description TEXT NOT NULL, due_at REAL,
        source_message_id TEXT, conversation_id TEXT, status TEXT DEFAULT 'OPEN',
        confidence REAL DEFAULT 0.5, created_at REAL, updated_at REAL, closed_at REAL)""",
    "CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status)",

    """CREATE TABLE IF NOT EXISTS reply_suggestions(
        id TEXT PRIMARY KEY, conversation_id TEXT, message_id TEXT, contact_id TEXT,
        options TEXT, context_summary TEXT, chosen_index INTEGER,
        sent_text TEXT, status TEXT DEFAULT 'NEW', created_at REAL, decided_at REAL)""",
)


def path():
    """Environment wins over the compiled default: tests get their own file."""
    return os.environ.get("ASSISTANT_DB") or config.db_path


def connect():
    """Thread-local connection: SQLite objects are not shareable across threads."""
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) != path():
        conn.close()
        conn = None
    if conn is None:
        conn = sqlite3.connect(path(), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
        _local.path = path()
    return conn


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def query(sql, params=()):
    return connect().execute(sql, params).fetchall()


def one(sql, params=()):
    return connect().execute(sql, params).fetchone()


def execute(sql, params=()):
    with tx() as conn:
        return conn.execute(sql, params)


# Tables whose names an earlier version of the assistant used with a different
# shape. They are set aside instead of dropped — the data may still be wanted.
LEGACY_GUARD = {"notifications": ("status", "severity", "channel")}


def _set_aside_incompatible(conn):
    for table, required in LEGACY_GUARD.items():
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone()
        if row is None:
            continue
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if columns and not set(required).issubset(columns):
            backup = f"{table}_legacy_{int(time.time())}"
            conn.execute(f"ALTER TABLE {table} RENAME TO {backup}")
            print(f"migration: {table} -> {backup} (старая схема)")


def migrate():
    conn = connect()
    _set_aside_incompatible(conn)
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()
    _prune_events()


def _prune_events():
    cutoff = time.time() - config.event_retention_days * 86400
    try:
        with tx() as conn:
            conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
    except sqlite3.Error:
        pass


def setting(key, default=None):
    row = one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?",
            (key, value, value))
