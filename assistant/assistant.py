#!/usr/bin/env python3
"""Personal assistant core: hybrid brain (local Ollama + Cursor gateway),
memory, and a finance skill. Channel-agnostic HTTP API; Telegram attaches later.
"""
import os, sqlite3, time, json, re, io, base64, wave, tempfile, threading
import datetime, zoneinfo
from contextlib import closing
import httpx
import news
import tgfmt
from fastapi import FastAPI, Body, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8791/v1")
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "")
GATEWAY_MODEL = os.environ.get("GATEWAY_MODEL", "cursor-grok-4.6-high-fast")
FINANCE_API = os.environ.get("FINANCE_API", "http://127.0.0.1/api/v1")
TG_USER_URL = os.environ.get("TG_USER_URL", "http://127.0.0.1:8810")
DB = os.environ.get("ASSISTANT_DB", "/opt/assistant/assistant.db")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "/opt/assistant/voices/ru_RU-dmitri-medium.onnx")
EXT_PROXY = os.environ.get("EXT_PROXY", "http://172.20.20.231:8080")
WEATHER_LAT = os.environ.get("WEATHER_LAT", "55.75")
WEATHER_LON = os.environ.get("WEATHER_LON", "37.62")
WEATHER_PLACE = os.environ.get("WEATHER_PLACE", "Москва")
TZ = zoneinfo.ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))
HISTORY = 12

WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря")

_whisper = None
_voice = None
_vlock = threading.Lock()


def get_whisper():
    global _whisper
    if _whisper is None:
        with _vlock:
            if _whisper is None:
                from faster_whisper import WhisperModel
                _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper


def get_voice():
    global _voice
    if _voice is None:
        with _vlock:
            if _voice is None:
                from piper import PiperVoice
                _voice = PiperVoice.load(PIPER_VOICE)
    return _voice


def stt_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        segments, _ = get_whisper().transcribe(path, language="ru", vad_filter=True)
        return "".join(s.text for s in segments).strip()
    finally:
        os.unlink(path)


def tts_wav(text: str) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        get_voice().synthesize_wav(text or "…", wf)
    return buf.getvalue()

PERSONA = (
    "Ты — Джарвис: личный ассистент одного человека (владельца этой системы). "
    "Ты работаешь на его домашнем сервере, поэтому говоришь как свой человек: "
    "спокойно, по-деловому, с лёгкой иронией, без подхалимства и без канцелярита.\n"
    "Язык — русский. Обращение — «ты».\n"
    "Ты не языковая модель и не рассказываешь о себе как об ИИ; ты просто ассистент."
)

PRINCIPLES = (
    "КАК ДУМАТЬ И ОТВЕЧАТЬ\n"
    "• Сначала ответ, потом детали. Первая строка — суть; если нужно, ниже раскрой.\n"
    "• Опирайся только на блок ДАННЫЕ и на факты о пользователе. Цифры, имена, "
    "заголовки и суммы не придумывай и не «уточняй» по памяти.\n"
    "• Данных нет — скажи прямо одной строкой и предложи, что подключить "
    "(почта, календарь, VK, Strava). Без извинений на три абзаца.\n"
    "• Не переспрашивай по мелочам: делай разумное допущение и помечай его. "
    "Уточняющий вопрос — только если без него ответ будет неверным, и только один.\n"
    "• Действия, которые что-то меняют или отправляют (письмо, пост, перевод), "
    "всегда сначала показывай черновиком и спрашивай подтверждение.\n"
    "• Приватные данные (переписки, почта, финансы, здоровье) обсуждай спокойно и "
    "по делу, не пересказывай лишнего и никогда не выводи токены, пароли и ключи.\n"
    "• Не морализируй, не читай лекции о безопасности, если не спросили."
)

STYLE_CHAT = (
    "ФОРМАТ (Telegram)\n"
    "• Разметка только HTML-теги: <b>жирный</b>, <i>курсив</i>, <code>код</code>, "
    "<a href=\"…\">ссылка</a>. Markdown (**, ##, ---, таблицы) запрещён.\n"
    "• Абзацы короткие, 1–2 строки. Между смысловыми блоками — пустая строка.\n"
    "• Списки: каждый пункт с новой строки, начинается с «• ». Не больше 7 пунктов.\n"
    "• Заголовок блока — <b>жирным</b>, можно с одним эмодзи в начале строки. "
    "Эмодзи — как маркер раздела, а не украшение в каждом предложении.\n"
    "• Деньги — «12 400 ₽», проценты — «+3,2%», время — «14:35», даты — «21 сентября».\n"
    "• По умолчанию укладывайся в 8 строк. Просят «подробно» — можно до 20.\n"
    "• Никаких вступлений вроде «Конечно!», «Вот что я нашёл» и подписей в конце."
)

STYLE_CHAT_LOCAL = (
    "ФОРМАТ (Telegram)\n"
    "• Коротко: 3–6 строк.\n"
    "• Пункты списка начинай с «• », каждый с новой строки.\n"
    "• Из разметки разрешены только <b>жирный</b> и <i>курсив</i>. "
    "Звёздочки, решётки, дефисы-маркеры и таблицы запрещены.\n"
    "• Деньги — «12 400 ₽». Без вступлений, без подписей, без повтора вопроса."
)

STYLE_VOICE = (
    "ФОРМАТ (голос)\n"
    "Ответ будет озвучен вслух. Поэтому: только простые фразы, никакой разметки, "
    "никаких ссылок, эмодзи, скобок и списков — вместо пунктов говори «во-первых», "
    "«ещё». Числа пиши словами там, где их неудобно читать вслух. "
    "Максимум 5–6 коротких предложений."
)

SKILLS = (
    "ЧТО У ТЕБЯ ЕСТЬ СЕЙЧАС\n"
    "• Финансы — данные приложения: капитал, динамика, бюджет.\n"
    "• Погода — по городу пользователя.\n"
    "• Новости — восемь лент, сгруппированные по темам, и сводки по ним.\n"
    "• Telegram — непрочитанные чаты и поиск по перепискам.\n"
    "• Голос — распознаёшь голосовые и отвечаешь голосом.\n"
    "Пока не подключены: почта, календарь, VK, Strava. "
    "Спросят про них — скажи, что этого ещё нет, и не выдумывай данные."
)

# Kept for backwards compatibility with older callers.
SYSTEM = "\n\n".join([PERSONA, PRINCIPLES, STYLE_CHAT])


def now_text():
    now = datetime.datetime.now(TZ)
    return (f"Сейчас {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS[now.month - 1]} "
            f"{now.year} года, {now:%H:%M} МСК. Город пользователя — {WEATHER_PLACE}.")


def build_system(channel="chat", blocks=(), facts="", brain="cursor"):
    """Assemble the system prompt: persona + rules + format + live context."""
    if channel == "voice":
        style = STYLE_VOICE
    else:
        # The 7B local model follows a short rule list far better than a long one.
        style = STYLE_CHAT_LOCAL if brain == "local" else STYLE_CHAT
    parts = [PERSONA, PRINCIPLES, style, SKILLS, "КОНТЕКСТ\n" + now_text()]
    if facts:
        parts.append("ФАКТЫ О ПОЛЬЗОВАТЕЛЕ (помни их, не переспрашивай)\n" + facts)
    data = [b for b in blocks if b]
    if data:
        parts.append("ДАННЫЕ (свежие, используй только их)\n" + "\n\n".join(data))
    # Last line wins with small models: repeat the rules that break most often.
    parts.append("НАПОМИНАНИЕ: обращайся на «ты» (не «вы»), по-русски, коротко, "
                 + ("простыми фразами без разметки."
                    if channel == "voice"
                    else "без markdown (никаких ** и ##). Цифры — только из ДАННЫХ."))
    return "\n\n".join(parts)

CURSOR_KEYWORDS = ("подробно", "разбор", "стратег", "план на", "сравни",
                   "почему", "анализ", "распиши", "детально", "объясни")
FINANCE_KEYWORDS = ("деньг", "бюджет", "расход", "доход", "трат", "накоп",
                    "капитал", "инвест", "подписк", "покупк", "кредит", "цел",
                    "финанс", "баланс")
NEWS_KEYWORDS = ("новост", "что нового", "в мире", "что происходит", "сводк",
                 "лент", "заголовк", "дайджест", "что интересного", "обзор дня")
TG_KEYWORDS = ("непрочит", "телеге", "телеграм", "кто писал", "в чат", "переписк")
WEATHER_KEYWORDS = ("погод", "дожд", "тепло ли", "холодно", "зонт", "градус")

# Intents that touch private data stay on the local model on principle.
PRIVATE_INTENTS = ("finance", "telegram")


def db_init():
    with closing(sqlite3.connect(DB)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS messages(session TEXT, role TEXT, content TEXT, ts REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, fact TEXT, ts REAL)")
        c.commit()


def mem_add(session, role, content):
    with closing(sqlite3.connect(DB)) as c:
        c.execute("INSERT INTO messages VALUES(?,?,?,?)", (session, role, content, time.time()))
        c.commit()


def mem_history(session, limit=HISTORY):
    with closing(sqlite3.connect(DB)) as c:
        rows = c.execute("SELECT role, content FROM messages WHERE session=? ORDER BY ts DESC LIMIT ?",
                         (session, limit)).fetchall()
    return [{"role": r, "content": t} for r, t in reversed(rows)]


def facts_text():
    with closing(sqlite3.connect(DB)) as c:
        rows = c.execute("SELECT fact FROM facts ORDER BY ts DESC LIMIT 20").fetchall()
    return "; ".join(r[0] for r in rows) if rows else ""


def is_finance(msg):
    m = msg.lower()
    return any(k in m for k in FINANCE_KEYWORDS)


def detect_intents(msg):
    """All intents the message touches; the first one is the primary."""
    m = msg.lower()
    found = []
    for name, keywords in (("finance", FINANCE_KEYWORDS), ("telegram", TG_KEYWORDS),
                           ("news", NEWS_KEYWORDS), ("weather", WEATHER_KEYWORDS)):
        if any(k in m for k in keywords):
            found.append(name)
    return found or ["general"]


def choose_brain(msg, override, intents=("general",)):
    """Private data -> local model. Public composition/reasoning -> Cursor."""
    if override in ("local", "cursor"):
        return override
    if any(i in PRIVATE_INTENTS for i in intents):
        return "local"
    m = msg.lower()
    if "news" in intents or len(msg) > 280 or any(k in m for k in CURSOR_KEYWORDS):
        return "cursor"
    return "local"


_ttl_cache = {}
_ttl_lock = threading.Lock()


def cached(key, ttl, producer):
    """Tiny TTL cache: external APIs over the proxy are slow, answers are not."""
    now = time.time()
    with _ttl_lock:
        hit = _ttl_cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    with _ttl_lock:
        _ttl_cache[key] = (now, value)
    return value


def money(value):
    """1234567.4 -> '1 234 567 ₽' (non-breaking thin spaces, no cents)."""
    try:
        return f"{round(float(value)):,}".replace(",", "\u202f") + " ₽"
    except (TypeError, ValueError):
        return "—"


def signed_money(value):
    try:
        num = round(float(value))
    except (TypeError, ValueError):
        return "—"
    return ("+" if num > 0 else "−" if num < 0 else "") + money(abs(num))


def finance_data():
    return cached("finance", 120, _finance_fetch)


def _finance_fetch():
    with httpx.Client(timeout=8, trust_env=False) as h:
        dash = h.get(f"{FINANCE_API}/dashboard").json()
        nw = h.get(f"{FINANCE_API}/networth").json()
        try:
            flow = h.get(f"{FINANCE_API}/analytics/cashflow").json()
        except Exception:
            flow = {}
    delta = nw.get("delta", {}) or {}
    amounts = {n.get("id"): n.get("amount") for n in (flow.get("nodes") or [])}
    return {"current": nw.get("current"), "month": delta.get("month"),
            "year": delta.get("year"), "widget": (dash.get("widget") or {}).get("title"),
            "income": amounts.get("income"), "expense": amounts.get("expense"),
            "invest": amounts.get("invest"), "savings": amounts.get("savings"),
            "free": amounts.get("free")}


def finance_context():
    try:
        d = finance_data()
        lines = [
            "Финансы пользователя (из его приложения):",
            f"- чистый капитал: {money(d['current'])}",
            f"- изменение за месяц: {signed_money(d['month'])}, за год: {signed_money(d['year'])}",
        ]
        if d.get("income") is not None:
            lines += [
                f"- доход за месяц: {money(d['income'])}",
                f"- расходы за месяц: {money(d['expense'])}",
                f"- в инвестиции: {money(d['invest'])}, в накопления: {money(d['savings'])}",
                f"- свободный остаток: {money(d['free'])}",
            ]
        if d.get("widget"):
            lines.append(f"- виджет дня в приложении: {d['widget']}")
        lines.append("Разбивки расходов по категориям и истории операций здесь нет — "
                     "если спросят, так и скажи и предложи посмотреть в приложении.")
        return "\n".join(lines)
    except Exception as e:
        return f"(финансовые данные недоступны: {e})"


def ext_get(url, timeout=12):
    """Fetch external URL: try direct first, fall back to proxy."""
    for kw in ({"trust_env": False}, {"proxy": EXT_PROXY}):
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (assistant)"}, **kw)
            if r.status_code == 200:
                return r
        except Exception:
            continue
    return None


WEATHER_ICONS = ((0, "☀️"), (3, "🌤"), (48, "🌫"), (67, "🌧"), (77, "🌨"),
                 (82, "🌧"), (86, "🌨"), (99, "⛈"))


def weather_icon(code):
    for limit, icon in WEATHER_ICONS:
        if code is not None and code <= limit:
            return icon
    return "🌡"


def weather_data():
    return cached("weather", 600, _weather_fetch)


def _weather_fetch():
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
           "&current=temperature_2m,apparent_temperature,wind_speed_10m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
           "&timezone=auto&forecast_days=1")
    d = ext_get(url).json()
    cur = d.get("current", {}) or {}
    day = d.get("daily", {}) or {}

    def first(key):
        return (day.get(key) or [None])[0]

    return {"now": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
            "wind": cur.get("wind_speed_10m"), "code": first("weather_code"),
            "max": first("temperature_2m_max"), "min": first("temperature_2m_min"),
            "rain": first("precipitation_probability_max"), "place": WEATHER_PLACE}


def weather_line(icon=True, data=None):
    """One dense line: '🌤 Москва: 17° (ощущается 17°), днём 14…21°, осадки 18%'."""
    w = data or weather_data()
    prefix = f"{weather_icon(w['code'])} " if icon else ""
    return (f"{prefix}{w['place']}: {w['now']:.0f}° "
            f"(ощущается {w['feels']:.0f}°), днём {w['min']:.0f}…{w['max']:.0f}°, "
            f"осадки {w['rain']:.0f}%, ветер {w['wind']:.0f} м/с")


def plural(n, one, few, many):
    """23 чата / 2 чата / 5 чатов — Russian numeral agreement."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def money_voice(value, signed=False):
    """Money the synthesiser can read out loud."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "неизвестно"
    sign = ("плюс " if num > 0 else "минус " if num < 0 else "") if signed else ""
    num = abs(num)
    if num >= 1_000_000:
        millions = num / 1_000_000
        text = f"{millions:.1f}".replace(".", ",").removesuffix(",0")
        return f"{sign}{text} {plural(round(millions), 'миллион', 'миллиона', 'миллионов')} рублей"
    if num >= 1000:
        thousands = round(num / 1000)
        return f"{sign}{thousands} {plural(thousands, 'тысяча', 'тысячи', 'тысяч')} рублей"
    return f"{sign}{round(num)} {plural(round(num), 'рубль', 'рубля', 'рублей')}"


def day_greeting(evening=False):
    """Greeting and icon that match the actual clock."""
    hour = datetime.datetime.now(TZ).hour
    if hour < 5:
        return "Доброй ночи", "🌙"
    if evening or hour >= 18:
        return "Добрый вечер", "🌙"
    if hour < 12:
        return "Доброе утро", "☀️"
    return "Добрый день", "🌇"


def weather_context():
    try:
        return "Погода. " + weather_line()
    except Exception as e:
        return f"(погода недоступна: {e})"


def news_items(limit=6):
    """Kept for compatibility: plain list of headlines."""
    _, shown = news.compose(limit=limit)
    return [s.title for s in shown]


def news_context(limit=8):
    try:
        return news.context(limit)
    except Exception as e:
        return f"(новости недоступны: {e})"


def tg_unread_context(limit=12):
    try:
        with httpx.Client(timeout=25, trust_env=False) as h:
            d = h.get(f"{TG_USER_URL}/unread", params={"limit": limit}).json()
        chats = d.get("chats", [])
        if not chats:
            return "Telegram: непрочитанных нет."
        lines = [f"• [{c['kind']}] {c['name']}: {c['unread']} — {c['last'][:80]}" for c in chats]
        return (f"Telegram: {d.get('total_unread_chats')} чатов с непрочитанными "
                f"({d.get('total_unread')} сообщений). Топ:\n" + "\n".join(lines))
    except Exception as e:
        return f"(Telegram недоступен: {e})"


def tg_unread_data(limit=6):
    with httpx.Client(timeout=25, trust_env=False) as h:
        return h.get(f"{TG_USER_URL}/unread", params={"limit": limit}).json()


def briefing_lead(data_blocks, evening=False):
    """One or two lines written by the brain: what actually matters today."""
    when = "вечер" if evening else "утро"
    prompt = (
        f"Ниже данные на {when}. Напиши РОВНО одну-две строки: что сегодня главное и "
        "на что обратить внимание. Без приветствия, без списков, без разметки, "
        "без повтора цифр целиком. Живым языком, как знакомый человек.\n\nДАННЫЕ:\n"
        + "\n\n".join(b for b in data_blocks if b)
    )
    messages = [{"role": "system", "content": build_system(channel="chat")},
                {"role": "user", "content": prompt}]
    for call in (call_cursor, call_ollama):
        try:
            line = call(messages).strip()
            if line:
                return re.sub(r"\s+", " ", line)[:400]
        except Exception:
            continue
    return ""


def compose_briefing(use_llm=True, fmt="html", evening=False, news_limit=6):
    """Deterministic layout + optional LLM lead, so the shape is always clean."""
    now = datetime.datetime.now(TZ)
    greet, icon = day_greeting(evening)
    head = f"{greet}! {WEEKDAYS[now.weekday()].capitalize()}, {now.day} {MONTHS[now.month - 1]}"

    weather_ico, weather = "🌤", "погода недоступна"
    try:
        wdata = weather_data()
        weather_ico = weather_icon(wdata["code"])
        weather = weather_line(icon=False, data=wdata)
    except Exception:
        pass
    try:
        fin = finance_data()
        fin_line = (f"{money(fin['current'])} · за месяц {signed_money(fin['month'])} · "
                    f"за год {signed_money(fin['year'])}")
    except Exception:
        fin_line = "данные приложения недоступны"
    try:
        news_block = news.render_flat(limit=news_limit, html=fmt == "html")
        news_data = news.context(news_limit)
    except Exception:
        news_block = news_data = ""
    try:
        tg = tg_unread_data(limit=4)
        chats = tg.get("chats") or []
        n_chats, n_msgs = tg.get("total_unread_chats", 0), tg.get("total_unread", 0)
        tg_line = (f"{n_chats} {plural(n_chats, 'чат', 'чата', 'чатов')}, "
                   f"{n_msgs} {plural(n_msgs, 'непрочитанное', 'непрочитанных', 'непрочитанных')}")
        tg_top = [f"{c['name']} ({c['unread']})" for c in chats[:3]]
    except Exception:
        tg_line, tg_top = "", []

    lead = ""
    if use_llm:
        lead = briefing_lead([f"Погода. {weather}", f"Финансы. {fin_line}", news_data,
                              f"Telegram. {tg_line}"], evening=evening)

    html = fmt == "html"

    def bold(text):
        return f"<b>{text}</b>" if html else text

    def italic(text):
        return f"<i>{text}</i>" if html else text

    out = [f"{icon} {bold(head)}", ""]
    if lead:
        out += [italic(lead), ""]
    out += [f"{weather_ico} {bold('Погода')}", weather, ""]
    out += [f"💰 {bold('Финансы')}", fin_line, ""]
    if news_block:
        out += [f"📰 {bold('Главное в новостях')}", news_block, ""]
    if tg_line:
        tail = (": " + ", ".join(tg_top)) if tg_top else ""
        out += [f"💬 {bold('Telegram')}", f"{tg_line}{tail}", ""]
    return "\n".join(out).strip()


def briefing_voice(evening=False, news_limit=4):
    """Spoken briefing: no markup, short sentences, numbers read naturally."""
    now = datetime.datetime.now(TZ)
    greet, _ = day_greeting(evening)
    parts = [f"{greet}! Сегодня {WEEKDAYS[now.weekday()]}, {now.day} {MONTHS[now.month - 1]}."]
    try:
        w = weather_data()
        parts.append(f"На улице {w['now']:.0f} "
                     f"{plural(round(w['now']), 'градус', 'градуса', 'градусов')}, "
                     f"днём до {w['max']:.0f}, осадки {w['rain']:.0f} процентов.")
    except Exception:
        pass
    try:
        fin = finance_data()
        parts.append(f"Капитал {money_voice(fin['current'])}, "
                     f"за месяц {money_voice(fin['month'], signed=True)}.")
    except Exception:
        pass
    try:
        parts.append(news.render_voice(limit=news_limit))
    except Exception:
        pass
    return " ".join(parts)


def call_ollama(messages):
    r = httpx.post(f"{OLLAMA_URL}/api/chat",
                   json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
                   timeout=300, trust_env=False)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def call_cursor(messages):
    r = httpx.post(f"{GATEWAY_URL}/chat/completions",
                   headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
                   json={"model": GATEWAY_MODEL, "messages": messages},
                   timeout=300, trust_env=False)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


app = FastAPI(title="Personal Assistant Core")


class ChatIn(BaseModel):
    text: str
    session: str = "default"
    brain: str = "auto"      # auto | local | cursor
    channel: str = "chat"    # chat | voice


def _warm_weather(period=540):
    """Open-meteo goes through the proxy and takes seconds; keep it pre-fetched."""
    def loop():
        while True:
            try:
                _ttl_cache.pop("weather", None)
                weather_data()
            except Exception:
                pass
            time.sleep(period)

    threading.Thread(target=loop, daemon=True, name="weather-warm").start()


@app.on_event("startup")
def _startup():
    db_init()
    news.start_background_refresh()
    _warm_weather()


@app.get("/health")
def health():
    ok_ollama = ok_gw = False
    try:
        ok_ollama = httpx.get(f"{OLLAMA_URL}/api/version", timeout=4, trust_env=False).status_code == 200
    except Exception:
        pass
    try:
        ok_gw = httpx.get(f"{GATEWAY_URL.rsplit('/v1',1)[0]}/health", timeout=4, trust_env=False).status_code == 200
    except Exception:
        pass
    try:
        news_stats = news.stats()
    except Exception as e:
        news_stats = {"error": str(e)}
    return {"status": "ok", "ollama": ok_ollama, "cursor_gateway": ok_gw,
            "model_local": OLLAMA_MODEL, "news": news_stats}


@app.post("/chat")
def chat(inp: ChatIn):
    intents = detect_intents(inp.text)
    intent = intents[0]
    brain = choose_brain(inp.text, inp.brain, intents)
    blocks = []
    if "finance" in intents:
        blocks.append(finance_context())
    if "weather" in intents:
        blocks.append(weather_context())
    if "news" in intents:
        blocks.append(news_context(8))
    if "telegram" in intents:
        blocks.append(tg_unread_context(12))
    system = build_system(channel=inp.channel, blocks=blocks,
                          facts=facts_text(), brain=brain)
    messages = [{"role": "system", "content": system}]
    messages += mem_history(inp.session)
    messages.append({"role": "user", "content": inp.text})
    try:
        reply = call_cursor(messages) if brain == "cursor" else call_ollama(messages)
    except Exception as e:
        # graceful cross-fallback: if one brain fails, try the other
        try:
            reply = call_ollama(messages) if brain == "cursor" else call_cursor(messages)
            brain = "local" if brain == "cursor" else "cursor"
        except Exception as e2:
            return {"reply": f"Мозг недоступен: {e}; {e2}", "brain": brain, "intent": intent, "error": True}
    mem_add(inp.session, "user", inp.text)
    mem_add(inp.session, "assistant", reply)
    return {"reply": reply, "brain": brain, "intent": intent, "intents": intents}


@app.get("/weather")
def api_weather():
    try:
        return {"text": weather_line(), "data": weather_data()}
    except Exception as e:
        return {"text": f"Погода недоступна: {e}", "error": True}


@app.get("/news")
def api_news(limit: int = 12, topic: str = None, per_topic: int = 3,
             links: bool = False, force: bool = False):
    """Grouped, deduplicated news: HTML for Telegram, text for anything else."""
    try:
        if force:
            news.collect(force=True)
        groups, shown = news.compose(limit=limit, topic=topic, per_topic=per_topic)
        return {
            "topic": topic or "all",
            "topics": news.available_topics(),
            "items": [s.as_dict() for s in shown],
            "titles": [s.title for s in shown],
            "html": news.render_html(groups=groups, topic=topic),
            "text": news.render_text(groups=groups, topic=topic, links=links),
            "voice": news.render_voice(limit=5),
            "stats": news.stats(),
        }
    except Exception as e:
        return {"error": True, "html": f"Новости недоступны: {e}", "text": f"Новости недоступны: {e}",
                "items": [], "titles": [], "topics": []}


@app.get("/news/digest")
def api_news_digest(limit: int = 14, brain: str = "auto"):
    """Headlines merged into a themed summary by the brain."""
    try:
        prompt, shown = news.digest_prompt(limit=limit)
        if not prompt:
            return {"html": "📰 Ленты сейчас недоступны — попробуй позже.", "brain": None}
        messages = [{"role": "system", "content": build_system(channel="chat")},
                    {"role": "user", "content": prompt}]
        order = [("cursor", call_cursor), ("local", call_ollama)]
        if brain == "local":
            order.reverse()
        errors = []
        for name, call in order:
            try:
                text = call(messages)
                stamp = datetime.datetime.now(TZ).strftime("%d.%m, %H:%M")
                header = f"<b>🧩 Сводка новостей · {stamp} МСК</b>\n\n"
                return {"html": header + tgfmt.to_html(text), "brain": name,
                        "used": len(shown)}
            except Exception as e:
                errors.append(f"{name}: {e}")
        return {"html": "Не удалось собрать сводку: " + "; ".join(errors), "error": True}
    except Exception as e:
        return {"html": f"Не удалось собрать сводку: {e}", "error": True}


@app.get("/briefing")
def api_briefing(raw: bool = False, fmt: str = "html", evening: bool = False):
    text = compose_briefing(use_llm=not raw, fmt=fmt, evening=evening)
    return {"text": text, "html": text if fmt == "html" else None,
            "voice": briefing_voice(evening=evening)}


@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    return {"text": stt_bytes(data)}


@app.post("/tts")
def tts(payload: dict = Body(...)):
    """Markup never reaches the synthesiser — it reads tags out loud otherwise."""
    return Response(content=tts_wav(tgfmt.plain(payload.get("text", ""))),
                    media_type="audio/wav")


@app.post("/voice")
async def voice(file: UploadFile = File(...), session: str = "default", brain: str = "auto"):
    data = await file.read()
    text_in = stt_bytes(data)
    res = chat(ChatIn(text=text_in, session=session, brain=brain, channel="voice"))
    wav = tts_wav(tgfmt.plain(res["reply"]))
    return {"text_in": text_in, "reply": res["reply"], "brain": res.get("brain"),
            "intent": res.get("intent"), "audio_b64": base64.b64encode(wav).decode()}
