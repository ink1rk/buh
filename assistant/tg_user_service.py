#!/usr/bin/env python3
"""Personal Telegram (user account) micro-service via Telethon over SOCKS5.

Exposes the owner's own Telegram to the assistant: unread summary, search,
channel posts (trading channels included), dialog history, and sending a reply
on his behalf. Incoming private messages are pushed to the assistant, which
prepares reply options. One long-lived authorized connection (session file).
"""
import os
import time

import httpx
from fastapi import FastAPI, Body
from telethon import TelegramClient, events, utils

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = os.environ.get("TG_SESSION", "/opt/assistant/tg_user.session")
SOCKS = os.environ.get("TG_SOCKS", "172.20.20.231:1080")
ASSISTANT = os.environ.get("ASSISTANT_URL", "http://127.0.0.1:8800")
NOTIFY = os.environ.get("TG_NOTIFY", "1") == "1"
NOTIFY_GROUPS = os.environ.get("TG_NOTIFY_GROUPS", "0") == "1"   # only mentions
NOTIFY_COOLDOWN = int(os.environ.get("TG_NOTIFY_COOLDOWN", "60"))  # per chat, seconds
PROXY = ("socks5", SOCKS.split(":")[0], int(SOCKS.split(":")[1]))

app = FastAPI(title="Telegram user account service")
client = TelegramClient(SESSION, API_ID, API_HASH, proxy=PROXY)
asst = httpx.AsyncClient(timeout=180, trust_env=False)

_last_notified: dict = {}


def kind_of(dialog):
    return "канал" if dialog.is_channel and not dialog.is_group else (
        "группа" if dialog.is_group else "личка")


@app.on_event("startup")
async def _startup():
    await client.connect()
    authorized = await client.is_user_authorized()
    print("tg-user connected:", client.is_connected(), "authorized:", authorized)
    if authorized and NOTIFY:
        client.add_event_handler(on_incoming, events.NewMessage(incoming=True))
        print("incoming-message notifications on")


async def on_incoming(event):
    """Push incoming DMs (and mentions) to the assistant for reply options."""
    try:
        if event.out:
            return
        private = event.is_private
        if not private:
            if not (NOTIFY_GROUPS and event.is_group and event.mentioned):
                return
        sender = await event.get_sender()
        if getattr(sender, "bot", False):
            return
        chat_id = event.chat_id
        now = time.time()
        if now - _last_notified.get(chat_id, 0) < NOTIFY_COOLDOWN:
            return
        _last_notified[chat_id] = now
        text = (event.raw_text or "").strip()
        if not text:
            text = "(вложение без текста)"
        history = []
        async for msg in client.iter_messages(chat_id, limit=14):
            if not (msg.raw_text or "").strip():
                continue
            history.append({"me": bool(msg.out), "text": msg.raw_text.strip()[:400],
                            "ts": msg.date.timestamp() if msg.date else 0})
        history.reverse()
        await asst.post(f"{ASSISTANT}/notify", json={
            "kind": "incoming_message",
            "peer_id": chat_id,
            "peer_name": utils.get_display_name(sender) or "неизвестный",
            "text": text[:1500],
            "history": history,
            "is_private": private,
        })
    except Exception as e:
        print("notify failed:", type(e).__name__, e)


@app.get("/health")
async def health():
    return {"status": "ok", "connected": client.is_connected(),
            "authorized": await client.is_user_authorized(),
            "notifications": NOTIFY}


@app.get("/unread")
async def unread(limit: int = 15):
    res = []
    async for d in client.iter_dialogs(limit=120):
        if d.unread_count and d.unread_count > 0:
            last = d.message.message if d.message and d.message.message else ""
            res.append({"name": d.name, "unread": d.unread_count,
                        "last": last[:160], "kind": kind_of(d), "peer_id": d.id})
    res.sort(key=lambda x: -x["unread"])
    return {"chats": res[:limit], "total_unread_chats": len(res),
            "total_unread": sum(x["unread"] for x in res)}


@app.get("/search")
async def search(q: str, limit: int = 10):
    out = []
    async for m in client.iter_messages(None, search=q, limit=limit):
        chat = getattr(m.chat, "title", None) or getattr(m.chat, "first_name", None) or "?"
        out.append({"date": str(m.date)[:16], "chat": chat, "text": (m.message or "")[:200]})
    return {"results": out}


@app.get("/dialogs")
async def dialogs(q: str = "", limit: int = 20):
    """Find chats/channels by name — used to resolve a channel once, by title."""
    needle = q.strip().lower()
    out = []
    async for d in client.iter_dialogs(limit=300):
        name = d.name or ""
        if needle and needle not in name.lower():
            continue
        out.append({"name": name, "peer_id": d.id, "kind": kind_of(d),
                    "unread": d.unread_count})
        if len(out) >= limit:
            break
    return {"dialogs": out}


async def resolve_peer(q=None, peer_id=None):
    if peer_id not in (None, 0, ""):
        return int(peer_id)
    needle = (q or "").strip().lower()
    if not needle:
        return None
    async for d in client.iter_dialogs(limit=300):
        if needle in (d.name or "").lower():
            return d.id
    return None


@app.get("/channel")
async def channel(q: str = "", peer_id: int = 0, limit: int = 12, hours: int = 48):
    """Recent posts of a channel, freshest first."""
    target = await resolve_peer(q, peer_id)
    if target is None:
        return {"error": f"канал не найден: {q}", "posts": []}
    cutoff = time.time() - hours * 3600
    entity = await client.get_entity(target)
    posts = []
    async for m in client.iter_messages(target, limit=max(limit * 3, 30)):
        text = (m.raw_text or "").strip()
        ts = m.date.timestamp() if m.date else 0
        if not text or ts < cutoff:
            continue
        posts.append({"text": text[:1200], "ts": ts,
                      "views": getattr(m, "views", None) or 0,
                      "id": m.id})
        if len(posts) >= limit:
            break
    return {"channel": utils.get_display_name(entity), "peer_id": target,
            "username": getattr(entity, "username", None), "posts": posts}


@app.get("/history")
async def history(peer_id: int, limit: int = 20):
    out = []
    async for m in client.iter_messages(peer_id, limit=limit):
        text = (m.raw_text or "").strip()
        if not text:
            continue
        out.append({"me": bool(m.out), "text": text[:600],
                    "ts": m.date.timestamp() if m.date else 0})
    out.reverse()
    entity = await client.get_entity(peer_id)
    return {"peer_id": peer_id, "name": utils.get_display_name(entity), "messages": out}


@app.post("/send")
async def send(payload: dict = Body(...)):
    """Send a message as the owner. Callers must confirm with the user first."""
    peer_id, text = payload.get("peer_id"), (payload.get("text") or "").strip()
    if not peer_id or not text:
        return {"error": "нужны peer_id и text"}
    try:
        msg = await client.send_message(int(peer_id), text)
        return {"ok": True, "message_id": msg.id}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@app.post("/read")
async def mark_read(payload: dict = Body(...)):
    try:
        await client.send_read_acknowledge(int(payload["peer_id"]))
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}
