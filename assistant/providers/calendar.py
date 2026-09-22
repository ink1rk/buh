#!/usr/bin/env python3
"""Календарь по CalDAV: чтение расписания и запись встреч.

Почему без библиотеки. Нужен узкий срез протокола: найти календари, забрать
события за окно, положить встречу. Повторы раскрывает сервер (`expand`), так
что клиенту не нужен разбор RRULE — самой тяжёлой части iCalendar. Остаётся
разбор нескольких полей VEVENT, и он здесь честно ограничен тем, что мы правда
читаем: всё непонятое лучше пропустить, чем показать владельцу выдумку.
"""
import datetime
import re
import uuid
import xml.etree.ElementTree as ET
import zoneinfo
from dataclasses import dataclass, field

import httpx

from core.actions import ActionProvider, ProviderError
from core.config import config

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav",
      "cs": "http://calendarserver.org/ns/"}

CALENDARS = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"
            xmlns:cs="http://calendarserver.org/ns/">
  <d:prop><d:resourcetype/><d:displayname/><cs:getctag/>
    <c:supported-calendar-component-set/></d:prop>
</d:propfind>"""

EVENTS = """<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><c:calendar-data><c:expand start="{start}" end="{end}"/></c:calendar-data></d:prop>
  <c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">
    <c:time-range start="{start}" end="{end}"/>
  </c:comp-filter></c:comp-filter></c:filter>
</c:calendar-query>"""

UTC = datetime.timezone.utc


# -- разбор iCalendar ------------------------------------------------------
def unfold(text):
    """Строка iCalendar длиннее 75 октетов переносится с отступом."""
    return re.sub(r"\r?\n[ \t]", "", text or "")


def unescape(value):
    out, escaped = [], False
    for char in value:
        if escaped:
            out.append({"n": "\n", "N": "\n"}.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            out.append(char)
    return "".join(out)


def parse_line(line):
    """`DTSTART;TZID=Europe/Moscow:20260903T110000` → имя, параметры, значение."""
    head, _, value = line.partition(":")
    parts = head.split(";")
    params = {}
    for chunk in parts[1:]:
        key, _, raw = chunk.partition("=")
        params[key.upper()] = raw.strip('"')
    return parts[0].upper(), params, value


def parse_moment(value, params, tz=None):
    """Момент времени VEVENT: с зоной, в UTC или дата целого дня.

    Возвращается всегда в часовом поясе владельца. Момент от этого не
    меняется, но меняется то, что он видит на часах: встреча, записанная
    как 20260924T010000Z, иначе показалась бы на три часа раньше.
    """
    tz = tz or config.tz
    value = (value or "").strip()
    if not value:
        return None, False
    if params.get("VALUE") == "DATE" or len(value) == 8:
        try:
            day = datetime.datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None, False
        # День целиком принадлежит календарю владельца, а не UTC.
        return day.replace(tzinfo=tz), True
    try:
        naive = datetime.datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        return None, False
    if value.endswith("Z"):
        return naive.replace(tzinfo=UTC).astimezone(tz), False
    zone = params.get("TZID")
    if zone:
        try:
            return (naive.replace(tzinfo=zoneinfo.ZoneInfo(zone)).astimezone(tz),
                    False)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass
    # Без зоны время считается местным: так его и задумывал автор события.
    return naive.replace(tzinfo=tz), False


@dataclass
class Event:
    uid: str = ""
    summary: str = ""
    start: datetime.datetime = None
    end: datetime.datetime = None
    all_day: bool = False
    location: str = ""
    description: str = ""
    status: str = ""
    organizer: str = ""
    attendees: list = field(default_factory=list)
    calendar: str = ""
    account: str = ""
    href: str = ""

    @property
    def cancelled(self):
        return self.status.upper() == "CANCELLED"

    def as_dict(self):
        return {"uid": self.uid, "summary": self.summary,
                "start": self.start.timestamp() if self.start else None,
                "end": self.end.timestamp() if self.end else None,
                "all_day": self.all_day, "location": self.location,
                "description": self.description[:500], "status": self.status,
                "attendees": self.attendees, "calendar": self.calendar,
                "account": self.account, "href": self.href}


# Поля, которые мы правда используем. Остальное сознательно не читаем.
TEXT_FIELDS = {"SUMMARY": "summary", "LOCATION": "location",
               "DESCRIPTION": "description", "STATUS": "status", "UID": "uid"}


def parse_events(raw, tz=None):
    """VEVENT из куска iCalendar. VTIMEZONE пропускаем: там свои DTSTART."""
    events = []
    for block in re.findall(r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT", unfold(raw), re.S):
        event = Event()
        for line in block.splitlines():
            if not line.strip():
                continue
            name, params, value = parse_line(line)
            if name in TEXT_FIELDS:
                setattr(event, TEXT_FIELDS[name], unescape(value).strip())
            elif name == "DTSTART":
                event.start, event.all_day = parse_moment(value, params, tz)
            elif name == "DTEND":
                event.end, _ = parse_moment(value, params, tz)
            elif name == "DURATION" and event.start and not event.end:
                event.end = event.start + parse_duration(value)
            elif name == "ORGANIZER":
                event.organizer = value.replace("mailto:", "").strip()
            elif name == "ATTENDEE":
                who = params.get("CN") or value.replace("mailto:", "")
                if who.strip():
                    event.attendees.append(who.strip())
        if event.start is None:
            continue                  # без начала это не встреча
        if event.end is None:
            event.end = (event.start + datetime.timedelta(days=1) if event.all_day
                         else event.start + datetime.timedelta(hours=1))
        events.append(event)
    return events


DURATION_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def parse_duration(value):
    match = DURATION_RE.fullmatch((value or "").strip().lstrip("+-"))
    if not match:
        return datetime.timedelta(hours=1)
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return datetime.timedelta(days=days, hours=hours, minutes=minutes,
                              seconds=seconds)


def build_event(summary, start, end=None, description="", location="",
                attendees=(), uid=None, tz=None):
    """Минимальный VEVENT. Время пишем в UTC: так его не переврёт ни один сервер."""
    tz = tz or config.tz
    uid = uid or f"{uuid.uuid4()}@jarvis"
    end = end or start + datetime.timedelta(hours=1)
    stamp = datetime.datetime.now(UTC)

    def moment(value):
        return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    def text(value):
        return (value or "").replace("\\", "\\\\").replace("\n", "\\n") \
            .replace(",", "\\,").replace(";", "\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jarvis//RU",
             "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{uid}",
             f"DTSTAMP:{moment(stamp)}", f"DTSTART:{moment(start)}",
             f"DTEND:{moment(end)}", f"SUMMARY:{text(summary)}"]
    if location:
        lines.append(f"LOCATION:{text(location)}")
    if description:
        lines.append(f"DESCRIPTION:{text(description)}")
    for who in attendees:
        lines.append(f"ATTENDEE;CN={text(who)}:mailto:{who}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return uid, "\r\n".join(lines) + "\r\n"


# -- CalDAV ----------------------------------------------------------------
@dataclass
class Collection:
    href: str
    name: str
    kind: str                         # VEVENT или VTODO
    ctag: str = ""


class CalDAV:
    """Один аккаунт CalDAV: список календарей, события за окно, запись встречи."""

    def __init__(self, account, cfg=None, client=None):
        self.account = account
        self.cfg = cfg or config.calendar
        self._client = client
        self._collections = None

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.Client(
                auth=httpx.BasicAuth(self.account.user, self.account.password),
                timeout=self.cfg.timeout, follow_redirects=True,
                headers={"User-Agent": "jarvis/1.0"})
        return self._client

    def _request(self, method, path, body, depth="1"):
        url = path if path.startswith("http") else f"{self.account.url}{path}"
        try:
            response = self.client.request(
                method, url, content=body.encode("utf-8"),
                headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"})
        except httpx.HTTPError as e:
            raise ProviderError(f"caldav: {type(e).__name__}: {e}", retryable=True)
        if response.status_code in (401, 403):
            raise ProviderError(
                f"{self.account.name}: логин или пароль не приняты "
                "(нужен пароль приложения, а не пароль аккаунта)", retryable=False)
        if response.status_code >= 400:
            raise ProviderError(f"caldav: {response.status_code}", retryable=False)
        return response

    def collections(self, refresh=False):
        if self._collections is not None and not refresh:
            return self._collections
        quoted = self.account.user.replace("@", "%40")
        response = self._request("PROPFIND", f"/calendars/{quoted}/", CALENDARS)
        found = []
        for node in ET.fromstring(response.text).findall("d:response", NS):
            href = (node.findtext("d:href", "", NS) or "").strip()
            resource = node.find(".//d:resourcetype", NS)
            if resource is None or resource.find("c:calendar", NS) is None:
                continue
            components = [c.get("name") for c
                          in node.findall(".//c:comp", NS)] or ["VEVENT"]
            found.append(Collection(
                href=href, name=node.findtext(".//d:displayname", "", NS) or href,
                kind=components[0],
                ctag=node.findtext(".//cs:getctag", "", NS) or ""))
        self._collections = found
        return found

    def events(self, start, end):
        window = {"start": start.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
                  "end": end.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")}
        events = []
        for collection in self.collections():
            if collection.kind != "VEVENT":
                continue
            response = self._request("REPORT", collection.href,
                                     EVENTS.format(**window))
            root = ET.fromstring(response.text)
            for node in root.findall("d:response", NS):
                data = node.findtext(".//c:calendar-data", "", NS)
                href = (node.findtext("d:href", "", NS) or "").strip()
                for event in parse_events(data):
                    if event.cancelled:
                        continue
                    event.calendar = collection.name
                    event.account = self.account.name
                    event.href = href
                    events.append(event)
        events.sort(key=lambda e: e.start)
        return events

    def create(self, summary, start, **options):
        target = options.pop("calendar", None)
        collection = self._pick(target)
        if collection is None:
            raise ProviderError("caldav: нет календаря для записи", retryable=False)
        uid, body = build_event(summary, start, **options)
        url = f"{self.account.url}{collection.href}{uid}.ics"
        try:
            response = self.client.put(
                url, content=body.encode("utf-8"),
                headers={"Content-Type": "text/calendar; charset=utf-8",
                         "If-None-Match": "*"})
        except httpx.HTTPError as e:
            raise ProviderError(f"caldav: {type(e).__name__}: {e}", retryable=True)
        if response.status_code >= 400:
            raise ProviderError(f"caldav: запись отклонена ({response.status_code})",
                                retryable=False)
        return {"uid": uid, "calendar": collection.name, "url": url}

    def _pick(self, name=None):
        calendars = [c for c in self.collections() if c.kind == "VEVENT"]
        if name:
            for item in calendars:
                if name.lower() in item.name.lower():
                    return item
        return calendars[0] if calendars else None

    def check(self):
        names = [c.name for c in self.collections(refresh=True)]
        if not names:
            raise ProviderError("caldav: календарей не найдено", retryable=False)
        return names


def clients(cfg=None):
    cfg = cfg or config.calendar
    return [CalDAV(account, cfg) for account in cfg.accounts]


class CalendarActionProvider(ActionProvider):
    """Запись встречи в календарь владельца."""

    action_types = ("create.calendar.event",)

    def __init__(self, cfg=None, factory=None):
        self.cfg = cfg or config.calendar
        self._factory = factory or (lambda account: CalDAV(account, self.cfg))

    def validate(self, action):
        if not self.cfg.enabled:
            raise ProviderError("календарь не настроен", retryable=False)
        params = action.parameters
        if not (params.get("summary") or "").strip():
            raise ProviderError("нужно название встречи", retryable=False)
        if not params.get("start"):
            raise ProviderError("нужно время начала", retryable=False)

    def execute(self, action):
        params = action.parameters
        account = self.cfg.account(params.get("account"))
        start = _moment(params["start"])
        end = _moment(params.get("end")) or start + datetime.timedelta(
            minutes=int(params.get("minutes") or 60))
        return self._factory(account).create(
            params["summary"].strip(), start, end=end,
            description=params.get("description", ""),
            location=params.get("location", ""),
            attendees=params.get("attendees") or (),
            calendar=params.get("calendar"))


def _moment(value):
    """Время приходит либо меткой, либо строкой ISO."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, config.tz)
    try:
        parsed = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        raise ProviderError(f"не понимаю время: {value}", retryable=False)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=config.tz)
