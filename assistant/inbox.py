#!/usr/bin/env python3
"""Incoming-message notifications with suggested replies.

tg-user pushes an incoming DM here; the assistant reads the recent history with
that person, asks the local model for a few replies in the owner's own manner,
and parks the result in a queue the Telegram bot drains. Suggestions are stored
so a button press can send one without re-generating anything.
"""
import json
import re
import sqlite3
import time
from contextlib import closing


class Inbox:
    def __init__(self, db_path, suggest):
        self.db = db_path
        self.suggest = suggest          # callable(peer_name, history, text) -> [str]
        self.init()

    def init(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT, peer_id TEXT, peer_name TEXT, text TEXT,
                suggestions TEXT, ts REAL, delivered INTEGER DEFAULT 0)""")
            c.commit()

    def add(self, kind, peer_id, peer_name, text, suggestions):
        with closing(sqlite3.connect(self.db)) as c:
            cur = c.execute(
                "INSERT INTO notifications(kind, peer_id, peer_name, text, suggestions, ts)"
                " VALUES(?,?,?,?,?,?)",
                (kind, str(peer_id), peer_name, text,
                 json.dumps(suggestions, ensure_ascii=False), time.time()))
            c.commit()
            return cur.lastrowid

    def pending(self, limit=10):
        with closing(sqlite3.connect(self.db)) as c:
            rows = c.execute(
                "SELECT id, kind, peer_id, peer_name, text, suggestions, ts FROM notifications"
                " WHERE delivered=0 ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "kind": r[1], "peer_id": r[2], "peer_name": r[3],
                 "text": r[4], "suggestions": json.loads(r[5] or "[]"), "ts": r[6]}
                for r in rows]

    def mark_delivered(self, ids):
        if not ids:
            return
        with closing(sqlite3.connect(self.db)) as c:
            c.executemany("UPDATE notifications SET delivered=1 WHERE id=?",
                          [(i,) for i in ids])
            c.commit()

    def get(self, notif_id):
        with closing(sqlite3.connect(self.db)) as c:
            row = c.execute(
                "SELECT id, peer_id, peer_name, text, suggestions FROM notifications"
                " WHERE id=?", (notif_id,)).fetchone()
        if not row:
            return None
        return {"id": row[0], "peer_id": row[1], "peer_name": row[2], "text": row[3],
                "suggestions": json.loads(row[4] or "[]")}

    def handle(self, payload):
        """Store an incoming message together with generated reply options."""
        text = (payload.get("text") or "").strip()
        peer_name = payload.get("peer_name") or "неизвестный"
        history = payload.get("history") or []
        try:
            options = self.suggest(peer_name, history, text)
        except Exception as e:
            print("suggest failed:", type(e).__name__, e)
            options = []
        notif_id = self.add(payload.get("kind", "incoming_message"),
                            payload.get("peer_id"), peer_name, text, options)
        return {"id": notif_id, "suggestions": options}


SUGGEST_PROMPT = (
    "Тебе пишет «{name}». Последнее сообщение:\n«{text}»\n\n"
    "Вот как вы общались до этого (ты — «Я»):\n{history}\n\n"
    "Задача: предложи ровно три варианта ответа ОТ МОЕГО ЛИЦА. Подстройся под мой "
    "стиль из переписки: та же длина, та же степень формальности, то же обращение.\n"
    "Вариант 1 — согласиться/поддержать, вариант 2 — уточнить или отложить, "
    "вариант 3 — короткий отказ или нейтральная отписка.\n"
    "Каждый вариант — одна строка без нумерации, без кавычек, без пояснений. "
    "Только три строки, ничего больше."
)


def format_history(history, limit=12):
    lines = []
    for item in history[-limit:]:
        who = "Я" if item.get("me") else "Он"
        text = re.sub(r"\s+", " ", (item.get("text") or "")).strip()
        if text:
            lines.append(f"{who}: {text[:300]}")
    return "\n".join(lines) or "(переписки ещё не было)"


def parse_options(reply, limit=3):
    """Pull clean one-liners out of whatever the model produced."""
    options = []
    for raw in (reply or "").splitlines():
        line = raw.strip()
        line = re.sub(r"^(вариант\s*)?\d+[\).:\-]?\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^[-*•]\s*", "", line).strip().strip('"«»')
        if len(line) < 2 or line.endswith(":"):
            continue
        if line.lower().startswith(("вот ", "конечно", "предлагаю", "варианты")):
            continue
        options.append(line[:300])
        if len(options) >= limit:
            break
    return options
