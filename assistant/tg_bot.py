#!/usr/bin/env python3
"""Telegram channel for the personal assistant.

Long-polls Telegram (via proxy), forwards text/voice to the local assistant core
and answers with formatted HTML plus voice. News come grouped by topic with
inline buttons (topics, AI digest, refresh). Only the configured owner is served.
"""
import os, base64, subprocess, tempfile, time, json, datetime, threading, traceback
import zoneinfo
from html import escape

import httpx
import tgfmt

TOKEN = os.environ["TG_TOKEN"].strip()
OWNER = int(os.environ["TG_ALLOWED_ID"])
ASSISTANT = os.environ.get("ASSISTANT_URL", "http://127.0.0.1:8800")
TG_USER_URL = os.environ.get("TG_USER_URL", "http://127.0.0.1:8810")
PROXY = os.environ.get("TG_PROXY", "http://172.20.20.231:8080")
TZ = zoneinfo.ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))
BRIEFING_TIME = os.environ.get("BRIEFING_TIME", "08:30")        # HH:MM local
EVENING_TIME = os.environ.get("EVENING_BRIEFING_TIME", "").strip()  # optional HH:MM
NEWS_LIMIT = int(os.environ.get("TG_NEWS_LIMIT", "12"))

API = f"https://api.telegram.org/bot{TOKEN}"
FILEAPI = f"https://api.telegram.org/file/bot{TOKEN}"

tg = httpx.Client(proxy=PROXY, timeout=70)           # Telegram API (needs proxy)
asst = httpx.Client(timeout=300, trust_env=False)     # local assistant (no proxy)

TOPIC_LABELS = {
    "world": "🌍 Мир", "russia": "🇷🇺 Россия", "econ": "💰 Экономика",
    "tech": "💻 Технологии", "science": "🔬 Наука", "sport": "⚽ Спорт",
    "culture": "🎬 Культура", "incident": "🚨 Происшествия", "other": "📌 Разное",
}

GREETING = (
    "<b>Привет! Я твой ассистент.</b>\n"
    "Пиши текстом или шли голосовое — отвечу тем же.\n\n"
    "<b>Команды</b>\n"
    "• /briefing — сводка дня: погода, финансы, новости, Telegram\n"
    "• /evening — вечерний вариант сводки\n"
    "• /news — новости по темам, с кнопками\n"
    "• /digest — то же, но пересказано своими словами\n"
    "• /weather — погода\n"
    "• /chats — непрочитанное в Telegram\n"
    "• /find &lt;текст&gt; — поиск по перепискам\n\n"
    "<i>Умею: финансы, погода, новости, твой Telegram. "
    "Дальше — почта, календарь, VK, спорт.</i>"
)


def api(method, **kw):
    """Telegram call with retries: the proxy hiccups now and then."""
    files = kw.pop("files", None)
    last = None
    for attempt in range(3):
        try:
            r = tg.post(f"{API}/{method}", data=kw, files=files)
            out = r.json()
            if out.get("ok"):
                return out
            last = out.get("description", "")
            if out.get("error_code") == 429:
                time.sleep(int((out.get("parameters") or {}).get("retry_after", 2)))
                continue
            return out
        except Exception as e:
            last = str(e)
            time.sleep(1.5 * (attempt + 1))
    return {"ok": False, "description": str(last)}


def send_html(chat_id, html, keyboard=None, preview=False):
    """Send HTML; on a parse error retry the same text as plain."""
    parts = tgfmt.split(html)
    result = None
    for index, part in enumerate(parts):
        payload = {"chat_id": chat_id, "text": part, "parse_mode": "HTML",
                   "disable_web_page_preview": not preview}
        if keyboard and index == len(parts) - 1:
            payload["reply_markup"] = json.dumps(keyboard)
        result = api("sendMessage", **payload)
        if not result.get("ok") and "parse" in str(result.get("description", "")).lower():
            payload.pop("parse_mode")
            payload["text"] = tgfmt.plain(part)
            result = api("sendMessage", **payload)
        if not result.get("ok"):
            print("sendMessage failed:", result.get("description"))
    return result


def send_text(chat_id, text):
    """Plain text in, formatted HTML out (models keep emitting markdown)."""
    return send_html(chat_id, tgfmt.to_html(text))


def edit_html(chat_id, message_id, html, keyboard=None, preview=False):
    parts = tgfmt.split(html)
    payload = {"chat_id": chat_id, "message_id": message_id, "text": parts[0],
               "parse_mode": "HTML", "disable_web_page_preview": not preview}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    res = api("editMessageText", **payload)
    error = str(res.get("description", "")).lower()
    if not res.get("ok") and "not modified" in error:
        return res
    if not res.get("ok") and "parse" in error:
        payload.pop("parse_mode")
        payload["text"] = tgfmt.plain(parts[0])
        res = api("editMessageText", **payload)
    for extra in parts[1:]:
        send_html(chat_id, extra)
    return res


def action(chat_id, act):
    try:
        api("sendChatAction", chat_id=chat_id, action=act)
    except Exception:
        pass


def typing_while(chat_id, act="typing"):
    """Keep the '…печатает' status alive while a slow answer is being built."""
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            action(chat_id, act)
            stop.wait(4)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def wav_to_ogg(wav: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav); inp = f.name
    out = inp + ".ogg"
    try:
        subprocess.run(["ffmpeg", "-y", "-i", inp, "-c:a", "libopus", "-b:a", "32k", out],
                       capture_output=True, check=True)
        return open(out, "rb").read()
    finally:
        for p in (inp, out):
            try: os.unlink(p)
            except OSError: pass


def send_voice(chat_id, wav: bytes, caption=None):
    try:
        ogg = wav_to_ogg(wav)
        api("sendVoice", chat_id=chat_id, caption=(caption or "")[:1000],
            files={"voice": ("reply.ogg", ogg, "audio/ogg")})
    except Exception as e:
        print("sendVoice failed:", e)


def tts(text: str) -> bytes:
    return asst.post(f"{ASSISTANT}/tts", json={"text": text}).content


def news_keyboard(topics, active=None):
    """Topic buttons (three per row) + digest/refresh row."""
    rows, row = [], []
    for key in topics:
        label = TOPIC_LABELS.get(key, key)
        if key == active:
            label = "· " + label + " ·"
        row.append({"text": label, "callback_data": f"news:{key}"})
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        {"text": "🧩 Сводка", "callback_data": "digest"},
        {"text": "📰 Все темы", "callback_data": "news:all"},
        {"text": "🔄 Обновить", "callback_data": f"refresh:{active or 'all'}"},
    ])
    return {"inline_keyboard": rows}


def fetch_news(topic=None, limit=NEWS_LIMIT, force=False):
    params = {"limit": limit, "force": str(bool(force)).lower()}
    if topic and topic != "all":
        params["topic"] = topic
        params["per_topic"] = limit
    return asst.get(f"{ASSISTANT}/news", params=params).json()


def send_news(chat_id, topic=None, message_id=None, force=False):
    stop = typing_while(chat_id)
    try:
        d = fetch_news(topic, force=force)
        html = d.get("html") or "Новости недоступны."
        keyboard = news_keyboard(d.get("topics") or [], active=topic)
        if message_id:
            edit_html(chat_id, message_id, html, keyboard)
        else:
            send_html(chat_id, html, keyboard)
    except Exception as e:
        traceback.print_exc()
        send_html(chat_id, f"Не получилось собрать новости: {escape(str(e))}")
    finally:
        stop.set()


def send_digest(chat_id):
    stop = typing_while(chat_id)
    try:
        d = asst.get(f"{ASSISTANT}/news/digest", timeout=300).json()
        brain = "🧠 Cursor" if d.get("brain") == "cursor" else "⚡ локальная модель"
        html = d.get("html", "")
        if not d.get("error"):
            html += f"\n\n<i>{brain}</i>"
        send_html(chat_id, html, news_keyboard(fetch_news().get("topics") or []))
    except Exception as e:
        traceback.print_exc()
        send_html(chat_id, f"Сводка не собралась: {escape(str(e))}")
    finally:
        stop.set()


def send_briefing(chat_id, evening=False, voice=True):
    stop = typing_while(chat_id)
    try:
        d = asst.get(f"{ASSISTANT}/briefing", params={"evening": str(evening).lower()}).json()
        send_html(chat_id, d.get("text", ""))
    except Exception as e:
        traceback.print_exc()
        send_html(chat_id, f"Брифинг не собрался: {escape(str(e))}")
        return
    finally:
        stop.set()
    if voice:
        action(chat_id, "record_voice")
        try:
            send_voice(chat_id, tts(d.get("voice") or d.get("text", "")))
        except Exception as e:
            print("briefing voice failed:", e)


def send_weather(chat_id):
    action(chat_id, "typing")
    d = asst.get(f"{ASSISTANT}/weather").json()
    send_html(chat_id, f"<b>Погода сейчас</b>\n{escape(d.get('text', ''))}")


def send_chats(chat_id):
    action(chat_id, "typing")
    try:
        d = asst.get(f"{TG_USER_URL}/unread", params={"limit": 15}).json()
    except Exception as e:
        return send_html(chat_id, f"Личный Telegram недоступен: {escape(str(e))}")
    chats = d.get("chats") or []
    if not chats:
        return send_html(chat_id, "💬 <b>Непрочитанного нет.</b> Чисто.")
    icons = {"личка": "👤", "группа": "👥", "канал": "📢"}
    lines = [f"💬 <b>Непрочитано</b> · {d.get('total_unread_chats', 0)} чатов · "
             f"{d.get('total_unread', 0)} сообщений"]
    for c in chats:
        icon = icons.get(c.get("kind"), "•")
        last = escape((c.get("last") or "").strip()[:90])
        lines.append(f"\n{icon} <b>{escape(c['name'])}</b> · {c['unread']}")
        if last:
            lines.append(f"<i>      {last}</i>")
    send_html(chat_id, "\n".join(lines))


def send_find(chat_id, query):
    action(chat_id, "typing")
    try:
        results = asst.get(f"{TG_USER_URL}/search",
                           params={"q": query, "limit": 10}).json().get("results", [])
    except Exception as e:
        return send_html(chat_id, f"Поиск недоступен: {escape(str(e))}")
    if not results:
        return send_html(chat_id, f"🔎 По запросу «{escape(query)}» ничего не нашлось.")
    lines = [f"🔎 <b>«{escape(query)}»</b> · найдено {len(results)}"]
    for r in results:
        lines.append(f"\n<b>{escape(r['chat'])}</b> · <i>{escape(r['date'])}</i>")
        lines.append(escape((r.get("text") or "").strip()[:250]))
    send_html(chat_id, "\n".join(lines))


def handle_command(chat_id, uid, text):
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1].strip() if len(parts) > 1 else ""
    if cmd in ("/start", "/help"):
        send_html(chat_id, GREETING)
    elif cmd == "/briefing":
        send_briefing(chat_id)
    elif cmd == "/evening":
        send_briefing(chat_id, evening=True)
    elif cmd == "/news":
        send_news(chat_id, arg.lower() if arg in TOPIC_LABELS else None)
    elif cmd == "/digest":
        send_digest(chat_id)
    elif cmd == "/weather":
        send_weather(chat_id)
    elif cmd == "/chats":
        send_chats(chat_id)
    elif cmd == "/find":
        if not arg:
            send_html(chat_id, "Как пользоваться: <code>/find текст</code>")
        else:
            send_find(chat_id, arg)
    else:
        return False
    return True


def handle_text(chat_id, uid, text):
    if text.startswith("/") and handle_command(chat_id, uid, text):
        return
    stop = typing_while(chat_id)
    try:
        d = asst.post(f"{ASSISTANT}/chat", json={"text": text, "session": f"tg:{uid}"}).json()
    finally:
        stop.set()
    tag = "🧠 cursor" if d.get("brain") == "cursor" else "⚡ локально"
    reply = tgfmt.to_html(d.get("reply") or "(пусто)")
    send_html(chat_id, f"{reply}\n\n<i>{tag}</i>")


def handle_voice(chat_id, uid, file_id):
    stop = typing_while(chat_id, "record_voice")
    try:
        fp = api("getFile", file_id=file_id).get("result", {}).get("file_path")
        if not fp:
            return send_html(chat_id, "Не удалось получить голосовое.")
        audio = tg.get(f"{FILEAPI}/{fp}").content
        d = asst.post(f"{ASSISTANT}/voice", params={"session": f"tg:{uid}"},
                      files={"file": ("voice.ogg", audio, "audio/ogg")}).json()
    finally:
        stop.set()
    heard = escape((d.get("text_in") or "").strip())
    send_html(chat_id, f"🗣 <i>«{heard}»</i>\n\n{tgfmt.to_html(d.get('reply') or '(пусто)')}")
    if d.get("audio_b64"):
        send_voice(chat_id, base64.b64decode(d["audio_b64"]))


def handle_callback(cb):
    data = cb.get("data") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    if data.startswith(("news:", "refresh:")):
        kind, topic = data.split(":", 1)
        api("answerCallbackQuery", callback_query_id=cb["id"],
            text="Обновляю…" if kind == "refresh" else "")
        send_news(chat_id, None if topic == "all" else topic,
                  message_id=message_id, force=kind == "refresh")
    elif data == "digest":
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Собираю сводку…")
        send_digest(chat_id)
    else:
        api("answerCallbackQuery", callback_query_id=cb["id"])


def scheduler():
    sent = {}
    while True:
        try:
            now = datetime.datetime.now(TZ)
            stamp, today = now.strftime("%H:%M"), now.strftime("%Y-%m-%d")
            for key, at, evening in (("morning", BRIEFING_TIME, False),
                                     ("evening", EVENING_TIME, True)):
                if at and stamp == at and sent.get(key) != today:
                    sent[key] = today
                    print(f"sending scheduled {key} briefing")
                    send_briefing(OWNER, evening=evening)
        except Exception:
            traceback.print_exc()
        time.sleep(20)


def setup_commands():
    api("setMyCommands", commands=json.dumps([
        {"command": "briefing", "description": "Сводка дня"},
        {"command": "evening", "description": "Вечерняя сводка"},
        {"command": "news", "description": "Новости по темам"},
        {"command": "digest", "description": "Сводка новостей своими словами"},
        {"command": "weather", "description": "Погода"},
        {"command": "chats", "description": "Непрочитанное в Telegram"},
        {"command": "find", "description": "Поиск по перепискам"},
        {"command": "start", "description": "О боте"},
    ]))


def main():
    print(f"telegram bot up for owner {OWNER}; briefing at {BRIEFING_TIME} {TZ}"
          + (f", evening at {EVENING_TIME}" if EVENING_TIME else ""))
    setup_commands()
    threading.Thread(target=scheduler, daemon=True).start()
    offset = None
    while True:
        try:
            upd = api("getUpdates", offset=offset, timeout=50,
                      allowed_updates=json.dumps(["message", "edited_message", "callback_query"]))
            if not upd.get("ok"):
                time.sleep(3); continue
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    cb = u["callback_query"]
                    if (cb.get("from") or {}).get("id") == OWNER:
                        try:
                            handle_callback(cb)
                        except Exception:
                            traceback.print_exc()
                    continue
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue
                uid = msg.get("from", {}).get("id")
                chat_id = msg["chat"]["id"]
                if uid != OWNER:
                    api("sendMessage", chat_id=chat_id, text="Этот ассистент приватный.")
                    continue
                try:
                    if "voice" in msg:
                        handle_voice(chat_id, uid, msg["voice"]["file_id"])
                    elif "text" in msg:
                        handle_text(chat_id, uid, msg["text"])
                    else:
                        send_html(chat_id, "Пришли текст или голосовое.")
                except Exception:
                    traceback.print_exc()
                    send_html(chat_id, "Ошибка при обработке. Попробуй ещё раз.")
        except Exception:
            traceback.print_exc()
            time.sleep(3)


if __name__ == "__main__":
    main()
