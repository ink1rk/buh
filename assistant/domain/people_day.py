#!/usr/bin/env python3
"""День с людьми — из переписки, которая уже приходит сама.

Telegram и почта стекаются в ядро без отдельной настройки на телефоне.
Отсюда видно, кто написал сегодня и кто ждёт ответа. Часы, журнал звонков
и выгрузка «Здоровья» для этого не нужны: их всё равно нельзя получить,
не поставив на телефон автоматизацию.
"""
import datetime
import time

from core import db
from core.config import config

from . import contacts

# Диалог владельца с самим ассистентом — не «человек ждёт ответа».
SKIP = {"telegram:bot"}
GRACE_MINUTES = 90
LOOKBACK_HOURS = 48


def day_start(now=None):
    now = now or time.time()
    moment = datetime.datetime.fromtimestamp(now, config.tz)
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp()


def _name(contact_id, title):
    if contact_id:
        contact = contacts.get(contact_id)
        if contact and contact.display_name:
            return contact.display_name
    return (title or "").strip() or "без имени"


def snapshot(now=None, grace_minutes=GRACE_MINUTES, lookback_hours=LOOKBACK_HOURS):
    """Кто писал сегодня и кто так и не дождался ответа."""
    now = now or time.time()
    since = now - lookback_hours * 3600
    today = day_start(now)
    rows = db.query(
        """SELECT m.conversation_id, m.sender_type, m.ts,
                  c.platform, c.title, c.contact_id
             FROM conv_messages m
             JOIN conversations c ON c.id = m.conversation_id
            WHERE m.ts >= ? AND m.sender_type != 'SYSTEM'
            ORDER BY m.ts""",
        (since,))

    latest = {}
    incoming = outgoing = 0
    people_today = set()
    for row in rows:
        if row["platform"] in SKIP:
            continue
        key = row["contact_id"] or row["conversation_id"]
        latest[key] = row
        if row["ts"] < today:
            continue
        people_today.add(key)
        if row["sender_type"] == "CONTACT":
            incoming += 1
        elif row["sender_type"] == "OWNER":
            outgoing += 1

    grace = grace_minutes * 60
    waiting = []
    for row in latest.values():
        if row["sender_type"] != "CONTACT":
            continue
        if now - row["ts"] < grace:
            continue
        waiting.append({
            "who": _name(row["contact_id"], row["title"]),
            "platform": row["platform"],
            "since": row["ts"],
            "hours_ago": round((now - row["ts"]) / 3600, 1),
        })
    waiting.sort(key=lambda item: item["since"])
    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "people": len(people_today),
        "waiting": waiting,
    }


def digest(now=None):
    """Одна строка для брифинга. Пусто — значит, говорить не о чем."""
    data = snapshot(now=now) if not isinstance(now, dict) else now
    parts = []
    if data["incoming"] or data["outgoing"]:
        parts.append(f"сегодня {data['incoming']} входящих, {data['outgoing']} исходящих")
    if data["waiting"]:
        names = []
        for item in data["waiting"][:4]:
            hours = item["hours_ago"]
            shown = f"{int(hours)} ч" if hours >= 1 else "недавно"
            names.append(f"{item['who']} ({shown})")
        parts.append("ждут ответа: " + ", ".join(names))
    return "; ".join(parts)


def context(now=None):
    """Блок в промпт. Без цитат: модели достаточно, кто и как давно."""
    data = snapshot(now=now)
    line = digest(data)
    if not line:
        return ""
    return "Люди. " + line + ". Это переписка, которая уже пришла сама — не телефон."
