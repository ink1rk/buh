#!/usr/bin/env python3
"""News collection and composition for the assistant.

Pulls several RSS feeds in parallel (direct, then through the proxy), drops
tabloid noise, merges stories that several outlets report at once, sorts them
into topics and renders compact digests for chat, Telegram HTML and voice.
"""
import datetime
import os
import re
import threading
import time
import zoneinfo
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html import escape, unescape

import httpx

EXT_PROXY = os.environ.get("EXT_PROXY", "http://172.20.20.231:8080")
TZ = zoneinfo.ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))
CACHE_TTL = int(os.environ.get("NEWS_CACHE_TTL", "300"))
DIRECT_TIMEOUT = float(os.environ.get("NEWS_DIRECT_TIMEOUT", "3.5"))
PROXY_TIMEOUT = float(os.environ.get("NEWS_PROXY_TIMEOUT", "9"))

# "Название|url" or "Название|url|тема" — тема forces the topic for that feed.
DEFAULT_FEEDS = (
    "Лента|https://lenta.ru/rss/news,"
    "Медуза|https://meduza.io/rss/all,"
    "РБК|https://rssexport.rbc.ru/rbcnews/news/30/full.rss,"
    "Интерфакс|https://www.interfax.ru/rss.asp,"
    "Коммерсантъ|https://www.kommersant.ru/RSS/news.xml,"
    "ТАСС|https://tass.ru/rss/v2.xml,"
    "Хабр|https://habr.com/ru/rss/news/?fl=ru|tech,"
    "N+1|https://nplus1.ru/rss|science"
)

TOPICS = (
    ("main", "Главное", "🔥"),
    ("world", "В мире", "🌍"),
    ("russia", "Россия", "🇷🇺"),
    ("econ", "Экономика", "💰"),
    ("tech", "Технологии", "💻"),
    ("science", "Наука", "🔬"),
    ("sport", "Спорт", "⚽"),
    ("culture", "Культура", "🎬"),
    ("incident", "Происшествия", "🚨"),
    ("other", "Разное", "📌"),
)
TOPIC_TITLE = {key: (title, emoji) for key, title, emoji in TOPICS}
TOPIC_ORDER = [key for key, _, _ in TOPICS]
TOPIC_KEYS = set(TOPIC_ORDER)

# RSS <category> values as the Russian outlets spell them.
CATEGORY_MAP = {
    "мир": "world", "в мире": "world", "весь мир": "world", "бывший ссср": "world",
    "международные отношения": "world", "международная панорама": "world",
    "украина": "world", "сша": "world", "европа": "world", "азия": "world",
    "россия": "russia", "в россии": "russia", "политика": "russia",
    "внутренняя политика": "russia", "общество": "russia", "москва": "russia",
    "регионы": "russia", "власть": "russia", "армия": "russia",
    "экономика": "econ", "бизнес": "econ", "финансы": "econ", "рынки": "econ",
    "деньги": "econ", "нефть": "econ", "инвестиции": "econ", "недвижимость": "econ",
    "промышленность": "econ", "потребительский рынок": "econ", "банки": "econ",
    "наука и техника": "tech", "технологии": "tech", "интернет и сми": "tech",
    "гаджеты": "tech", "софт": "tech", "техника": "tech", "ит-бизнес": "tech",
    "телекоммуникации": "tech", "it": "tech",
    "наука": "science", "медицина": "science", "космос": "science",
    "здоровье": "science", "экология": "science",
    "спорт": "sport", "футбол": "sport", "хоккей": "sport", "бокс и mma": "sport",
    "олимпиада": "sport",
    "культура": "culture", "кино": "culture", "музыка": "culture", "театр": "culture",
    "искусство": "culture", "книги": "culture", "шоубиз": "culture",
    "происшествия": "incident", "силовые структуры": "incident", "криминал": "incident",
    "следствие и суд": "incident", "преступность": "incident", "чп": "incident",
}

# Word-prefix stems: matched at word starts only, so "цен" won't hit "ценности".
TOPIC_STEMS = {
    "econ": ("рубл", "инфляц", "ставк", "бюджет", "налог", "нефт", "газ", "биржа",
             "акци", "ипотек", "банк", "цен", "подорожа", "подешеве", "кредит",
             "экспорт", "импорт", "доллар", "евро", "юан", "вклад", "зарплат",
             "пенси", "маркетплейс", "тариф", "пошлин", "торгов", "выручк", "прибыл",
             "инвест", "займ", "субсиди", "эконом"),
    "tech": ("нейросет", "искусственн", "чип", "процессор", "смартфон", "iphone",
             "android", "google", "apple", "microsoft", "openai", "telegram",
             "интернет", "приложени", "хакер", "утечк", "робот", "гаджет",
             "программист", "серверн", "дата-центр", "стартап", "llm", "gpt",
             "чат-бот", "алгоритм"),
    "science": ("учён", "учен", "исследован", "космос", "спутник", "марс", "луна",
                "вакцин", "вирус", "препарат", "клиническ", "физик", "геном",
                "телескоп", "археолог", "палеонтолог"),
    "sport": ("матч", "чемпионат", "турнир", "олимпи", "футбол", "хоккей", "теннис",
              "тренер", "сборн", "рпл", "биатлон", "шахмат", "марафон", "цска",
              "зенит", "спартак", "нхл", "уефа", "фифа"),
    "culture": ("фильм", "сериал", "премьер", "концерт", "выставк", "спектакл",
                "режиссёр", "режиссер", "актёр", "актер", "альбом", "оскар",
                "книг", "музе", "театр"),
    "incident": ("погиб", "пожар", "дтп", "авари", "взрыв", "задержа", "арестова",
                 "уголовн", "приговор", "мошенник", "убий", "стрельб", "обруш",
                 "пострада", "затоплен", "эвакуац", "беспилотник", "теракт", "ранен"),
    "world": ("сша", "трамп", "евросоюз", "нато", "китай", "германи", "франци",
              "британи", "израил", "иран", "турци", "япони", "индия", "польш",
              "саммит", "переговор", "санкц", "оон", "киев", "зеленск", "брюссел"),
    "russia": ("путин", "кремл", "госдум", "минобороны", "мид", "правительств",
               "совфед", "мишустин", "росси", "москв", "петербург"),
}
TOPIC_RE = {
    topic: re.compile(r"(?:^|[^а-яёa-z])(?:" + "|".join(stems) + r")", re.IGNORECASE)
    for topic, stems in TOPIC_STEMS.items()
}

SKIP_CATEGORIES = {
    s.strip().lower()
    for s in os.environ.get(
        "NEWS_SKIP_CATEGORIES",
        "из жизни,ценности,стиль,забота о себе,дом,путешествия,библиотека,"
        "шоу-бизнес,светская хроника,гороскоп,биографии и справки,база знаний,"
        "инфографика,partner,реклама",
    ).split(",")
    if s.strip()
}

JUNK_PATTERNS = [
    r"показал[аи]?\s+(фигур|груд|тело|ягодиц|бикини|нижнем|прессом|попу)",
    r"в\s+(откровенн\w*\s+)?(бикини|купальник\w*|прозрачн\w*)",
    r"раскрыл[аи]?\s+(вес|возраст|размер)",
    r"гороскоп|астролог|нумеролог|таро|приворот",
    r"похудел[аи]?\s+на\s",
    r"дом[- ]?2|шоу-бизнес",
    r"на\s+правах\s+рекламы|партн[её]рский\s+материал",
    r"^как\s+правильно\s",
]
_extra_junk = os.environ.get("NEWS_JUNK_EXTRA", "").strip()
if _extra_junk:
    JUNK_PATTERNS += [re.escape(w.strip()) for w in _extra_junk.split(",") if w.strip()]
JUNK_RE = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)

# Clickbait phrasing: kept in the feed, but pushed out of the "Главное" block.
FLUFF_RE = re.compile(
    r"^(назван|назвал|раскры|стало известно|появил|рассказал|сообщил)|"
    r"(назван[ыао]|раскры\w+|рассказал[аи]?|показал[аи]?|оценил[аи]?|"
    r"призвал[аи]?|пожаловал\w+|удивил\w+)\b",
    re.IGNORECASE,
)
# Stories worth putting on top.
WEIGHTY_RE = re.compile(
    r"(путин|санкц|ставк|инфляц|переговор|соглашени|указ|закон|запрет|теракт|"
    r"погиб|пострада|взрыв|катастроф|рубл|цб|бюджет|мобилизац|перемири|"
    r"курс\s+(доллар|евро)|отставк|назначен|дефолт|обвал|рекорд)",
    re.IGNORECASE,
)

STOPWORDS = {
    "и", "в", "на", "с", "по", "из", "за", "о", "об", "от", "для", "не", "что", "как",
    "к", "у", "до", "при", "же", "а", "но", "это", "его", "её", "их", "был", "была",
    "были", "будет", "стал", "стала", "после", "под", "над", "про", "все", "всё",
    "может", "почти", "более", "менее", "году", "года", "стало", "своей", "свои",
}

_cache = {"ts": 0.0, "items": []}
_lock = threading.Lock()
_routes: dict = {}          # host -> "direct" | "proxy", learned at runtime
_refresher = None


@dataclass
class Story:
    title: str
    link: str
    source: str
    ts: float
    topic: str = "other"
    summary: str = ""
    sources: list = field(default_factory=list)

    @property
    def all_sources(self):
        return [self.source] + [s for s in self.sources if s != self.source]

    def when(self):
        """Human-friendly freshness marker, Moscow time."""
        if not self.ts:
            return ""
        delta = max(0.0, time.time() - self.ts)
        if delta < 3600:
            return f"{max(1, int(delta // 60))} мин назад"
        if delta < 6 * 3600:
            return f"{int(delta // 3600)} ч назад"
        return datetime.datetime.fromtimestamp(self.ts, TZ).strftime("%d.%m %H:%M")

    def as_dict(self):
        title, emoji = TOPIC_TITLE.get(self.topic, ("Разное", "📌"))
        return {
            "title": self.title, "link": self.link, "sources": self.all_sources,
            "topic": self.topic, "topic_title": title, "topic_emoji": emoji,
            "ts": self.ts, "when": self.when(), "summary": self.summary,
        }


def feeds():
    raw = os.environ.get("NEWS_FEEDS") or DEFAULT_FEEDS
    out = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) == 1:
            url = parts[0]
            host = (httpx.URL(url).host or url).replace("www.", "")
            out.append((host.split(".")[0].title(), url, None))
        elif len(parts) == 2:
            out.append((parts[0], parts[1], None))
        else:
            out.append((parts[0], parts[1], parts[2] if parts[2] in TOPIC_KEYS else None))
    return out


def _fetch(url):
    """Direct first, then via proxy; remember which route works per host."""
    headers = {"User-Agent": "Mozilla/5.0 (assistant)", "Accept": "application/rss+xml,*/*"}
    host = httpx.URL(url).host
    attempts = [("direct", {"trust_env": False}, DIRECT_TIMEOUT),
                ("proxy", {"proxy": EXT_PROXY}, PROXY_TIMEOUT)]
    if _routes.get(host) == "proxy":
        attempts.reverse()
    for route, kw, timeout in attempts:
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers, **kw)
            if r.status_code == 200 and r.content:
                _routes[host] = route
                return r.content
        except Exception:
            continue
    return None


def _clean(text):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _entry_ts(entry):
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            try:
                return time.mktime(tm) - time.timezone
            except Exception:
                continue
    return 0.0


def _categories(entry):
    cats = []
    for tag in entry.get("tags") or []:
        term = (tag.get("term") or "").strip().lower()
        if not term:
            continue
        cats.append(term)
        # "Технологии / ИТ-бизнес" -> both halves
        cats += [p.strip() for p in term.split("/") if p.strip()]
    return cats


def classify(title, summary, link, cats, forced=None):
    if forced:
        return forced
    for cat in cats:
        if cat in CATEGORY_MAP:
            return CATEGORY_MAP[cat]
        for part in cat.split("/"):           # "Технологии / ИТ-бизнес"
            if part.strip() in CATEGORY_MAP:
                return CATEGORY_MAP[part.strip()]
    path = (link or "").lower()
    for marker, topic in (("/sport", "sport"), ("/econom", "econ"), ("/ekonomik", "econ"),
                          ("/business", "econ"), ("/finance", "econ"), ("/tech", "tech"),
                          ("/science", "science"), ("/nauka", "science"),
                          ("/culture", "culture"), ("/kultura", "culture"),
                          ("/incident", "incident"), ("/proisshestv", "incident"),
                          ("/world", "world"), ("/mezhdunarodnaya", "world"),
                          ("/politic", "russia"), ("/politika", "russia"),
                          ("/obschestvo", "russia"), ("/armiya", "russia")):
        if marker in path:
            return topic
    # The headline decides; the summary only breaks ties, otherwise unrelated
    # words in the lead paragraph drag stories into the wrong section.
    for text in (title, summary or ""):
        scores = {topic: len(rx.findall(text)) for topic, rx in TOPIC_RE.items()}
        scores = {t: n for t, n in scores.items() if n}
        if scores:
            # "russia" is the weakest signal: almost every local story mentions Russia.
            return max(scores.items(), key=lambda kv: (kv[1], kv[0] != "russia"))[0]
    return "other"


def is_junk(title, cats):
    return any(c in SKIP_CATEGORIES for c in cats) or bool(JUNK_RE.search(title))


def _tokens(title):
    words = re.findall(r"[а-яёa-z0-9]+", title.lower())
    return {w[:5] for w in words if len(w) > 3 and w not in STOPWORDS}


def _same_story(a, b):
    if not a or not b:
        return False
    inter = len(a & b)
    return inter / len(a | b) >= 0.4 or inter >= max(4, min(len(a), len(b)) - 1)


def collect(force=False):
    """Fetch every feed in parallel; return deduplicated stories, freshest first."""
    with _lock:
        fresh = _cache["items"] and time.time() - _cache["ts"] < CACHE_TTL
    if fresh and not force:
        return _cache["items"]

    import feedparser

    def one(spec):
        name, url, forced = spec
        raw = _fetch(url)
        if not raw:
            return []
        out = []
        for entry in feedparser.parse(raw).entries[:40]:
            title = _clean(entry.get("title"))
            if len(title) < 12:
                continue
            cats = _categories(entry)
            if is_junk(title, cats):
                continue
            summary = _clean(entry.get("summary") or entry.get("description"))[:300]
            link = (entry.get("link") or "").strip()
            out.append(Story(title=title, link=link, source=name, ts=_entry_ts(entry),
                             summary=summary,
                             topic=classify(title, summary, link, cats, forced)))
        return out

    specs = feeds()
    stories = []
    with ThreadPoolExecutor(max_workers=max(2, len(specs))) as pool:
        for chunk in pool.map(one, specs):
            stories.extend(chunk)

    stories.sort(key=lambda s: -s.ts)
    merged, index = [], []
    for story in stories:
        toks = _tokens(story.title)
        for existing, existing_toks in zip(merged, index):
            if _same_story(toks, existing_toks):
                if story.source not in existing.all_sources:
                    existing.sources.append(story.source)
                if existing.topic in ("other", "russia") and story.topic not in ("other", "russia"):
                    existing.topic = story.topic
                break
        else:
            merged.append(story)
            index.append(toks)

    if merged:
        with _lock:
            _cache["items"] = merged
            _cache["ts"] = time.time()
    return merged or _cache["items"]


def score(story):
    """Higher = more digest-worthy: several outlets, weighty wording, still fresh."""
    age_h = (time.time() - story.ts) / 3600 if story.ts else 6.0
    value = len(story.all_sources) * 3.0 - min(max(age_h, 0.0), 12.0) * 0.35
    if WEIGHTY_RE.search(story.title):
        value += 2.0
    if FLUFF_RE.search(story.title):
        value -= 2.5
    if story.topic in ("world", "russia", "econ"):
        value += 0.7
    if story.topic == "other":
        value -= 0.7
    return value


def compose(limit=12, topic=None, per_topic=3, fresh_hours=24, highlights_n=3):
    """Pick and group stories: a 'Главное' block plus per-topic sections."""
    cutoff = time.time() - fresh_hours * 3600
    items = [s for s in collect() if not s.ts or s.ts >= cutoff]
    single_topic = topic not in (None, "all", "main")
    if single_topic:
        items = [s for s in items if s.topic == topic]
        items.sort(key=lambda s: -score(s))
        picked = items[:limit]
        return ({topic: picked} if picked else {}), picked

    ranked = sorted(items, key=lambda s: -score(s))
    highlights = ranked[:highlights_n]
    if topic == "main":
        return ({"main": highlights} if highlights else {}), highlights

    used = {id(s) for s in highlights}
    groups, shown = {}, list(highlights)
    per_source = {}
    for s in highlights:
        per_source[s.source] = per_source.get(s.source, 0) + 1
    source_cap = max(2, limit // 3)      # keep one wire service from taking over
    for story in items:
        if id(story) in used or len(shown) >= limit:
            continue
        bucket = groups.setdefault(story.topic, [])
        if len(bucket) >= per_topic or per_source.get(story.source, 0) >= source_cap:
            continue
        bucket.append(story)
        shown.append(story)
        used.add(id(story))
        per_source[story.source] = per_source.get(story.source, 0) + 1

    ordered = {}
    if highlights:
        ordered["main"] = highlights
    for key in TOPIC_ORDER:
        if key != "main" and groups.get(key):
            ordered[key] = groups[key]
    return ordered, shown


def _header(total, topic=None):
    now = datetime.datetime.now(TZ).strftime("%d.%m, %H:%M")
    if topic and topic not in ("all", "main"):
        title, emoji = TOPIC_TITLE.get(topic, ("Разное", "📌"))
        return f"{emoji} {title} · {total} шт · {now} МСК"
    return f"📰 Новости · {total} шт · {now} МСК"


def render_html(limit=12, topic=None, groups=None):
    """Telegram HTML: topic headers, clickable headlines, source + freshness."""
    if groups is None:
        groups, _ = compose(limit=limit, topic=topic)
    if not groups:
        return "📰 Пока нечего показать: ленты недоступны или новостей по теме нет."
    total = sum(len(v) for v in groups.values())
    lines = [f"<b>{escape(_header(total, topic))}</b>"]
    for key, stories in groups.items():
        title, emoji = TOPIC_TITLE.get(key, ("Разное", "📌"))
        lines.append(f"\n{emoji} <b>{escape(title)}</b>")
        for s in stories:
            head = escape(s.title)
            if s.link:
                head = f'<a href="{escape(s.link, quote=True)}">{head}</a>'
            meta = " · ".join(x for x in [", ".join(s.all_sources), s.when()] if x)
            bullet = "🔸" if len(s.all_sources) > 1 else "▫️"
            lines.append(f"{bullet} {head}\n<i>      {escape(meta)}</i>")
    return "\n".join(lines)


def render_text(limit=12, topic=None, groups=None, links=False):
    """Plain-text version for non-HTML channels."""
    if groups is None:
        groups, _ = compose(limit=limit, topic=topic)
    if not groups:
        return "Новости недоступны."
    total = sum(len(v) for v in groups.values())
    lines = [_header(total, topic)]
    for key, stories in groups.items():
        title, emoji = TOPIC_TITLE.get(key, ("Разное", "📌"))
        lines.append(f"\n{emoji} {title}")
        for s in stories:
            meta = " · ".join(x for x in [", ".join(s.all_sources), s.when()] if x)
            lines.append(f"• {s.title}\n      {meta}")
            if links and s.link:
                lines.append(f"      {s.link}")
    return "\n".join(lines)


def render_flat(limit=5, html=True):
    """Flat top-N list with a topic emoji per line — for briefings."""
    _, shown = compose(limit=limit, highlights_n=limit)
    if not shown:
        return "Ленты недоступны."
    lines = []
    for s in shown[:limit]:
        emoji = TOPIC_TITLE.get(s.topic, ("Разное", "📌"))[1]
        meta = " · ".join(x for x in [", ".join(s.all_sources), s.when()] if x)
        if html:
            head = escape(s.title)
            if s.link:
                head = f'<a href="{escape(s.link, quote=True)}">{head}</a>'
            lines.append(f"{emoji} {head}\n<i>      {escape(meta)}</i>")
        else:
            lines.append(f"{emoji} {s.title}\n      {meta}")
    return "\n".join(lines)


def render_voice(limit=5):
    """Spoken version: no links, no meta, plain sentences."""
    _, shown = compose(limit=limit, highlights_n=limit)
    if not shown:
        return "Новости сейчас недоступны."
    parts = ["Коротко о главном."]
    for s in shown[:limit]:
        parts.append(s.title.rstrip(".") + ".")
    return " ".join(parts)


def context(limit=8):
    """Compact block for LLM prompts and the briefing."""
    groups, shown = compose(limit=limit, per_topic=2)
    if not shown:
        return "Новости: ленты недоступны."
    lines = ["Новости (заголовки лент, свежие сверху):"]
    for key, stories in groups.items():
        title = TOPIC_TITLE.get(key, ("Разное", "📌"))[0]
        for s in stories:
            lines.append(f"- [{title}] {s.title} ({', '.join(s.all_sources)}, {s.when()})")
    return "\n".join(lines)


def digest_prompt(limit=14):
    """Prompt that asks the brain to merge headlines into a themed digest."""
    groups, shown = compose(limit=limit, per_topic=3)
    if not shown:
        return None, []
    raw = []
    for key, stories in groups.items():
        title, emoji = TOPIC_TITLE.get(key, ("Разное", "📌"))
        for s in stories:
            raw.append(f"[{emoji} {title}] {s.title} ({', '.join(s.all_sources)}, {s.when()})")
    prompt = (
        "Ниже сырые заголовки новостных лент. Собери из них сводку по-русски.\n"
        "Правила формата:\n"
        "1. Группируй по темам. Тема — отдельная строка вида «<b>💰 Экономика</b>» "
        "(эмодзи бери из квадратных скобок заголовка).\n"
        "2. Под темой 1–3 пункта, каждый начинается с «• ». Один пункт — одна мысль, "
        "своими словами, не длиннее двух строк.\n"
        "3. Если несколько заголовков об одном событии — объедини в один пункт.\n"
        "4. Максимум 4 темы и 8 пунктов. Ничего не добавляй от себя, только то, "
        "что есть в заголовках.\n"
        "5. Последняя строка — «<i>Вывод:</i> …»: одно предложение о том, что здесь важно.\n"
        "6. Никакого markdown (** ## -), только текст и теги <b>/<i>. Без ссылок.\n\n"
        "ЗАГОЛОВКИ:\n" + "\n".join(raw)
    )
    return prompt, shown


def available_topics(fresh_hours=24):
    """Topic keys that currently have stories, for inline keyboards."""
    cutoff = time.time() - fresh_hours * 3600
    present = {s.topic for s in collect() if not s.ts or s.ts >= cutoff}
    return [k for k in TOPIC_ORDER if k in present and k != "main"]


def stats():
    items = collect()
    hour_ago = time.time() - 3600
    return {
        "total": len(items),
        "last_hour": sum(1 for s in items if s.ts and s.ts >= hour_ago),
        "sources": sorted({src for s in items for src in s.all_sources}),
        "cached_at": _cache["ts"],
    }


def start_background_refresh(interval=None):
    """Keep the cache warm so /news answers instantly."""
    global _refresher
    if _refresher and _refresher.is_alive():
        return
    period = interval or CACHE_TTL

    def loop():
        while True:
            try:
                collect(force=True)
            except Exception:
                pass
            time.sleep(period)

    _refresher = threading.Thread(target=loop, daemon=True, name="news-refresh")
    _refresher.start()


if __name__ == "__main__":
    t0 = time.time()
    print(render_text(limit=14))
    print(f"\n[fetched in {time.time() - t0:.1f}s; {stats()}]")
    print("\n--- voice ---\n" + render_voice())
