#!/usr/bin/env python3
"""Audit log: who did what, on whose approval, with what result.

Everything the assistant does on the owner's behalf lands here, tied together
by correlation_id so the Activity timeline can replay a whole chain.
"""
import json
import time

from . import db

SENSITIVE = ("password", "token", "secret", "api_key", "apikey", "authorization",
             "cookie", "credential", "pass")


def _sanitize(value):
    """Never let credentials into the log, however deep they are nested."""
    if isinstance(value, dict):
        return {k: ("***" if any(s in str(k).lower() for s in SENSITIVE) else _sanitize(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def record(event, actor="system", correlation_id=None, entity_type=None,
           entity_id=None, details=None, level="info"):
    payload = json.dumps(_sanitize(details or {}), ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO audit_log(ts, correlation_id, actor, event, entity_type,"
        " entity_id, details, level) VALUES(?,?,?,?,?,?,?,?)",
        (time.time(), correlation_id, actor, event, entity_type,
         str(entity_id) if entity_id is not None else None, payload, level))


def timeline(limit=50, correlation_id=None, since=None):
    sql = "SELECT * FROM audit_log"
    conditions, params = [], []
    if correlation_id:
        conditions.append("correlation_id=?")
        params.append(correlation_id)
    if since:
        conditions.append("ts>=?")
        params.append(since)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = db.query(sql, tuple(params))
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.get("details") or "{}")
        except ValueError:
            item["details"] = {}
        out.append(item)
    return out


def subscribe(bus):
    """Mirror every event into the audit log — the timeline needs both."""
    def handler(event):
        record(event.type, actor=event.source, correlation_id=event.correlation_id,
               entity_type="event", entity_id=event.id, details=event.payload)

    bus.subscribe("*", handler, name="audit")
    return handler
