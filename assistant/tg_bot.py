#!/usr/bin/env python3
"""Telegram channel for the personal assistant.

Long-polls Telegram (via proxy) and talks to the local core over HTTP. Voice
messages are transcribed and answered with text — the assistant never replies
with audio. News come grouped by topic with inline buttons.
Only the configured owner is served.
"""
import os, time, json, datetime, threading, traceback
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
NOTIFY_POLL = int(os.environ.get("TG_NOTIFY_POLL", "5"))        # seconds

API = f"https://api.telegram.org/bot{TOKEN}"
FILEAPI = f"https://api.telegram.org/file/bot{TOKEN}"

tg = httpx.Client(proxy=PROXY, timeout=70)           # Telegram API (needs proxy)
asst = httpx.Client(timeout=300, trust_env=False)     # local assistant (no proxy)

pending_reply: dict = {}     # set when the owner chooses «своими словами»

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
    "• /trading — сводка по каналу Full-Time Trading\n"
    "• /weather — погода\n"
    "• /chats — непрочитанное в Telegram\n"
    "• /inbox — кто ждёт ответа и что я обещал\n"
    "• /who Имя — карточка контакта\n"
    "• /memory [запрос] — что я помню\n"
    "• /activity — журнал действий\n"
    "• /status — состояние интеграций\n"
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


def send_briefing(chat_id, evening=False):
    stop = typing_while(chat_id)
    try:
        d = asst.get(f"{ASSISTANT}/briefing", params={"evening": str(evening).lower()}).json()
        send_html(chat_id, d.get("text", ""))
    except Exception as e:
        traceback.print_exc()
        send_html(chat_id, f"Брифинг не собрался: {escape(str(e))}")
    finally:
        stop.set()


def send_trading(chat_id, hours=24):
    stop = typing_while(chat_id)
    try:
        d = asst.get(f"{ASSISTANT}/trading", params={"hours": hours}, timeout=300).json()
        send_html(chat_id, d.get("html") or "Канал недоступен.")
    except Exception as e:
        traceback.print_exc()
        send_html(chat_id, f"Сводка по каналу не собралась: {escape(str(e))}")
    finally:
        stop.set()


def suggestion_keyboard(notification):
    """SEND / EDIT / IGNORE for suggested replies."""
    meta = notification.get("metadata") or {}
    suggestion_id = meta.get("suggestion_id")
    rows = []
    for index in range(len(meta.get("options") or [])):
        rows.append([{"text": f"📨 Отправить {index + 1}",
                      "callback_data": f"snd:{suggestion_id}:{index}"}])
    rows.append([{"text": "✍️ Свой ответ", "callback_data": f"own:{suggestion_id}"},
                 {"text": "🙈 Пропустить", "callback_data": f"ign:{suggestion_id}"}])
    return {"inline_keyboard": rows}


def approval_keyboard(notification):
    action_id = (notification.get("metadata") or {}).get("action_id")
    return {"inline_keyboard": [[
        {"text": "✅ Подтвердить", "callback_data": f"apr:{action_id}"},
        {"text": "❌ Отменить", "callback_data": f"cnl:{action_id}"}]]}


def render_incoming(notification):
    meta = notification.get("metadata") or {}
    lines = [f"💬 <b>{escape(notification.get('title') or 'Сообщение')}</b>",
             f"<i>«{escape((notification.get('body') or '')[:700])}»</i>"]
    summary = meta.get("context_summary")
    if summary:
        lines.append(f"\n<i>Контекст: {escape(summary[:300])}</i>")
    options = meta.get("options") or []
    if options:
        lines.append("\nВарианты ответа:")
        for index, option in enumerate(options, 1):
            lines.append(f"<b>{index}.</b> {escape(option)}")
    else:
        lines.append("\n<i>Вариантов нет — ответь своими словами.</i>")
    return "\n".join(lines)


def render_approval(notification):
    meta = notification.get("metadata") or {}
    return (f"⚠️ <b>Требуется подтверждение</b>\n\n"
            f"Действие: <code>{escape(meta.get('action_type', '?'))}</code>\n"
            f"Риск: {escape(str(meta.get('risk', '?')))}\n\n"
            f"<i>{escape((notification.get('body') or '')[:600])}</i>")


def deliver(notification):
    kind = (notification.get("metadata") or {}).get("kind")
    if kind == "incoming_message":
        send_html(OWNER, render_incoming(notification), suggestion_keyboard(notification))
    elif kind == "approval":
        send_html(OWNER, render_approval(notification), approval_keyboard(notification))
    else:
        body = notification.get("body") or ""
        title = notification.get("title") or "Уведомление"
        send_html(OWNER, f"<b>{escape(title)}</b>\n{escape(body[:900])}")


def notification_poller():
    """Drain the core notification queue: the core has no Telegram token."""
    while True:
        try:
            items = asst.get(f"{ASSISTANT}/api/notifications/pending",
                             params={"limit": 5}).json().get("items") or []
            delivered = []
            for notification in items:
                try:
                    deliver(notification)
                    delivered.append(notification["id"])
                except Exception:
                    traceback.print_exc()
            if delivered:
                asst.post(f"{ASSISTANT}/api/notifications/delivered",
                          json={"ids": delivered})
        except Exception:
            pass
        time.sleep(NOTIFY_POLL)


def send_suggestion(chat_id, suggestion_id, index=None, text=None):
    payload = {"index": index} if text is None else {"text": text}
    d = asst.post(f"{ASSISTANT}/api/suggestions/{suggestion_id}/send",
                  json=payload, timeout=120).json()
    if d.get("status") == "SUCCESS":
        send_html(chat_id, f"✅ Отправлено <b>{escape(str(d.get('contact', '')))}</b>:\n"
                           f"<i>«{escape(d.get('text', ''))}»</i>")
    else:
        send_html(chat_id, "Не отправилось: "
                           + escape(str(d.get("error") or d.get("status"))))


def approve_action(chat_id, action_id, approve=True):
    verb = "approve" if approve else "cancel"
    d = asst.post(f"{ASSISTANT}/api/actions/{action_id}/{verb}", json={}, timeout=120).json()
    status = d.get("status", "?")
    if status == "SUCCESS":
        send_html(chat_id, "✅ Выполнено.")
    elif status == "CANCELLED":
        send_html(chat_id, "❌ Отменено.")
    elif status == "EXPIRED":
        send_html(chat_id, "⌛️ Подтверждение просрочено — запроси действие заново.")
    else:
        send_html(chat_id, f"Статус: {escape(status)}. "
                           + escape(str(d.get("error") or "")))


def send_inbox(chat_id):
    """Единый почтовый ящик коммуникаций: кто ждёт, кому должен."""
    try:
        waiting = asst.get(f"{ASSISTANT}/api/commitments",
                           params={"status": "OPEN"}).json().get("commitments") or []
        conversations = asst.get(f"{ASSISTANT}/api/conversations",
                                 params={"limit": 8}).json().get("conversations") or []
    except Exception as e:
        return send_html(chat_id, f"Не собралось: {escape(str(e))}")
    mine = [c for c in waiting if c["direction"] == "I_OWE"]
    theirs = [c for c in waiting if c["direction"] == "THEY_OWE"]
    lines = ["📥 <b>Коммуникации</b>"]
    if mine:
        lines.append("\n<b>Я должен ответить/сделать</b>")
        for item in mine[:8]:
            who = item.get("counterparty_name") or "—"
            lines.append(f"• {escape(item['description'])} <i>({escape(who)})</i>")
    if theirs:
        lines.append("\n<b>Жду ответа</b>")
        for item in theirs[:8]:
            who = item.get("counterparty_name") or "—"
            lines.append(f"• {escape(who)}: {escape(item['description'])}")
    talks = [c for c in conversations if c.get("platform") == "telegram"]
    if talks:
        lines.append("\n<b>Последние диалоги</b>")
        for conversation in talks[:6]:
            name = conversation.get("contact_name") or conversation.get("title") or "чат"
            summary = (conversation.get("summary") or "")[:140]
            lines.append(f"▫️ <b>{escape(name)}</b>"
                         + (f"\n<i>      {escape(summary)}</i>" if summary else ""))
    if len(lines) == 1:
        lines.append("\nПусто: никто ничего не ждёт.")
    send_html(chat_id, "\n".join(lines))


def send_commitments(chat_id):
    d = asst.get(f"{ASSISTANT}/api/commitments", params={"status": "OPEN"}).json()
    items = d.get("commitments") or []
    if not items:
        return send_html(chat_id, "Открытых обязательств нет.")
    lines = ["🤝 <b>Обязательства</b>"]
    for item in items[:20]:
        arrow = "→" if item["direction"] == "I_OWE" else "←"
        who = item.get("counterparty_name") or "—"
        lines.append(f"{arrow} {escape(item['description'])} <i>({escape(who)})</i>")
    send_html(chat_id, "\n".join(lines))


def send_contact_card(chat_id, name):
    if not name:
        return send_html(chat_id, "Кого показать? Например: <code>/who Сергей</code>")
    d = asst.get(f"{ASSISTANT}/api/contacts/resolve", params={"q": name}).json()
    if d.get("ambiguous"):
        options = "\n".join(f"• {escape(c['display_name'])}"
                            for c in d.get("candidates", [])[:5])
        return send_html(chat_id, f"Нашла несколько:\n{options}\n\nУточни, кто нужен.")
    contact = d.get("resolved")
    if not contact:
        return send_html(chat_id, "Такого контакта пока нет.")
    profile = asst.get(f"{ASSISTANT}/api/contacts/{contact['id']}/context").json()
    lines = [f"👤 <b>{escape(contact['display_name'])}</b>"]
    if contact.get("aliases"):
        lines.append(f"<i>также: {escape(', '.join(contact['aliases'][:5]))}</i>")
    lines.append(f"Отношения: {escape(contact.get('relationship_type', 'UNKNOWN').lower())}")
    style = contact.get("communication_style") or {}
    if style:
        lines.append(f"Стиль: {escape(str(style.get('length')))}, "
                     f"{escape(str(style.get('formality')))}")
    for commitment in (profile.get("commitments") or [])[:6]:
        arrow = "→" if commitment["direction"] == "I_OWE" else "←"
        lines.append(f"{arrow} {escape(commitment['description'])}")
    memories = profile.get("memories") or []
    if memories:
        lines.append("\n<b>Помню:</b>")
        for memory in memories[:6]:
            lines.append(f"• {escape(memory['content'])}")
    send_html(chat_id, "\n".join(lines))


def send_memory(chat_id, query):
    if query:
        d = asst.post(f"{ASSISTANT}/api/memory/search", json={"query": query}).json()
        items = d.get("results") or []
        head = f"🧠 <b>Память по «{escape(query)}»</b>"
    else:
        d = asst.get(f"{ASSISTANT}/api/memory", params={"limit": 15}).json()
        items = d.get("memories") or []
        head = "🧠 <b>Что я помню</b>"
    if not items:
        return send_html(chat_id, head + "\n\nПока пусто.")
    lines = [head]
    for memory in items[:15]:
        mark = "?" if memory.get("source") == "LLM_INFERENCE" else "•"
        lines.append(f"{mark} <b>{escape(memory['type'].lower())}</b>: "
                     f"{escape(memory['content'][:220])}"
                     f"\n<i>      {escape(memory['source'].lower())}, "
                     f"уверенность {memory.get('confidence', 0):.2f}</i>")
    send_html(chat_id, "\n".join(lines))


def send_activity(chat_id):
    d = asst.get(f"{ASSISTANT}/api/activity", params={"limit": 15}).json()
    items = d.get("activity") or []
    if not items:
        return send_html(chat_id, "Журнал пуст.")
    lines = ["🧾 <b>Что происходило</b>"]
    for item in items:
        stamp = datetime.datetime.fromtimestamp(item["ts"], TZ).strftime("%H:%M:%S")
        lines.append(f"<code>{stamp}</code> {escape(item['event'])}")
    send_html(chat_id, "\n".join(lines))


def send_status(chat_id):
    d = asst.get(f"{ASSISTANT}/api/integrations", params={"refresh": "true"}).json()
    marks = {"CONNECTED": "🟢", "DEGRADED": "🟡", "ERROR": "🔴",
             "NOT_CONFIGURED": "⚪️", "DISABLED": "⚫️"}
    lines = ["🩺 <b>Интеграции</b>"]
    for item in d.get("integrations") or []:
        mark = marks.get(item["status"], "⚪️")
        lines.append(f"{mark} <b>{escape(item['name'])}</b> — "
                     f"{escape(str(item.get('detail') or item['status'])[:80])}")
    send_html(chat_id, "\n".join(lines))


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
    elif cmd in ("/trading", "/trade"):
        hours = int(arg) if arg.isdigit() else 24
        send_trading(chat_id, hours)
    elif cmd == "/inbox":
        send_inbox(chat_id)
    elif cmd in ("/todo", "/commitments"):
        send_commitments(chat_id)
    elif cmd == "/who":
        send_contact_card(chat_id, arg)
    elif cmd == "/memory":
        send_memory(chat_id, arg)
    elif cmd == "/activity":
        send_activity(chat_id)
    elif cmd in ("/status", "/integrations"):
        send_status(chat_id)
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


def core_chat(text, uid, message_type="TEXT", transcription=None):
    """Everything the owner says goes through the same core pipeline."""
    return asst.post(f"{ASSISTANT}/api/chat",
                     json={"text": text, "session": f"tg:{uid}", "interface": "telegram",
                           "message_type": message_type,
                           "transcription": transcription}).json()


def handle_text(chat_id, uid, text):
    if text.startswith("/") and handle_command(chat_id, uid, text):
        return
    if pending_reply.get("suggestion_id") and not text.startswith("/"):
        target = pending_reply.copy()
        pending_reply.clear()
        return send_suggestion(chat_id, target["suggestion_id"], text=text)
    stop = typing_while(chat_id)
    try:
        d = core_chat(text, uid)
    finally:
        stop.set()
    tag = "🧠 cursor" if d.get("provider") == "cursor" else "⚡ локально"
    reply = tgfmt.to_html(d.get("reply") or "(пусто)")
    send_html(chat_id, f"{reply}\n\n<i>{tag}</i>")


def handle_voice(chat_id, uid, file_id):
    """Voice in → transcription → same pipeline → text out. Never audio back."""
    stop = typing_while(chat_id)
    try:
        fp = api("getFile", file_id=file_id).get("result", {}).get("file_path")
        if not fp:
            return send_html(chat_id, "Не удалось получить голосовое.")
        audio = tg.get(f"{FILEAPI}/{fp}").content
        heard = (asst.post(f"{ASSISTANT}/stt",
                           files={"file": ("voice.ogg", audio, "audio/ogg")})
                 .json().get("text") or "").strip()
        if not heard:
            return send_html(chat_id, "Не разобрала, что в голосовом.")
        d = core_chat(heard, uid, message_type="VOICE", transcription=heard)
    finally:
        stop.set()
    send_html(chat_id, f"🗣 <i>«{escape(heard)}»</i>\n\n"
                       f"{tgfmt.to_html(d.get('reply') or '(пусто)')}")


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
    elif data.startswith("snd:"):
        _, suggestion_id, index = data.split(":")
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Отправляю…")
        send_suggestion(chat_id, suggestion_id, index=int(index))
    elif data.startswith("own:"):
        suggestion_id = data.split(":", 1)[1]
        suggestion = asst.get(f"{ASSISTANT}/api/suggestions/{suggestion_id}").json()
        if suggestion.get("id"):
            pending_reply.update({"suggestion_id": suggestion_id,
                                  "name": suggestion.get("contact_name", "")})
            api("answerCallbackQuery", callback_query_id=cb["id"], text="Жду текст")
            send_html(chat_id, "✍️ Напиши ответ для "
                               f"<b>{escape(suggestion.get('contact_name', ''))}</b> "
                               "следующим сообщением — отправлю как есть.")
        else:
            api("answerCallbackQuery", callback_query_id=cb["id"], text="Не нашла чат")
    elif data.startswith("ign:"):
        suggestion_id = data.split(":", 1)[1]
        asst.post(f"{ASSISTANT}/api/suggestions/{suggestion_id}/ignore", json={})
        api("answerCallbackQuery", callback_query_id=cb["id"], text="Ок, пропускаю")
        if message_id:
            api("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                reply_markup=json.dumps({"inline_keyboard": []}))
    elif data.startswith(("apr:", "cnl:")):
        kind, action_id = data.split(":", 1)
        api("answerCallbackQuery", callback_query_id=cb["id"],
            text="Выполняю…" if kind == "apr" else "Отменяю…")
        approve_action(chat_id, action_id, approve=(kind == "apr"))
        if message_id:
            api("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                reply_markup=json.dumps({"inline_keyboard": []}))
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
        {"command": "trading", "description": "Сводка трейдинг-канала"},
        {"command": "inbox", "description": "Кто ждёт ответа"},
        {"command": "who", "description": "Карточка контакта"},
        {"command": "memory", "description": "Что помнит ассистент"},
        {"command": "activity", "description": "Журнал действий"},
        {"command": "status", "description": "Состояние интеграций"},
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
    threading.Thread(target=notification_poller, daemon=True).start()
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
