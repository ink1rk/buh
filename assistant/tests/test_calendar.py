"""Календарь: разбор iCalendar, CalDAV и запись встречи."""
import datetime
import zoneinfo

import pytest

from core.actions import ProviderError
from core.config import CalDAVAccount, CalendarConfig
from providers.calendar import (CalDAV, CalendarActionProvider, build_event,
                                parse_duration, parse_events, unfold)

MSK = zoneinfo.ZoneInfo("Europe/Moscow")
ACCOUNT = CalDAVAccount(name="yandex", user="kirill@yandex.ru", password="secret",
                        url="https://caldav.yandex.ru")


def settings(**overrides):
    return CalendarConfig(accounts=(ACCOUNT,), **overrides)


# Как это приходит от Яндекса на самом деле.
YANDEX = """BEGIN:VCALENDAR
PRODID:-//Yandex LLC//Yandex Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
TZID:Europe/Moscow
BEGIN:STANDARD
TZNAME:MSK
TZOFFSETFROM:+0300
TZOFFSETTO:+0300
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:event-1@yandex.ru
SUMMARY:Созвон с подрядчиком
DTSTART;TZID=Europe/Moscow:20260922T150000
DTEND;TZID=Europe/Moscow:20260922T160000
LOCATION:Zoom
END:VEVENT
END:VCALENDAR"""


def test_a_yandex_event_is_read_with_its_timezone():
    event, = parse_events(YANDEX)

    assert event.summary == "Созвон с подрядчиком"
    assert event.start == datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK)
    assert event.end == datetime.datetime(2026, 9, 22, 16, 0, tzinfo=MSK)
    assert event.location == "Zoom" and not event.all_day


def test_the_timezone_block_is_not_mistaken_for_an_event():
    """У VTIMEZONE свои DTSTART — наивный разбор превращал их во встречи."""
    assert len(parse_events(YANDEX)) == 1


def test_a_folded_line_is_read_whole():
    """Строка длиннее 75 октетов переносится с отступом — иначе имя обрежется."""
    raw = ("BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Очень длинное название встречи про\r\n"
           "  смету и подрядчика\r\nDTSTART:20260922T120000Z\r\nEND:VEVENT")
    event, = parse_events(raw)
    assert event.summary == "Очень длинное название встречи про смету и подрядчика"


def test_unfolding_leaves_ordinary_lines_alone():
    assert unfold("A:1\r\nB:2") == "A:1\r\nB:2"


def test_escaped_text_is_restored():
    raw = ("BEGIN:VEVENT\r\nUID:x\r\nDTSTART:20260922T120000Z\r\n"
           "SUMMARY:Смета\\, счёт\\; и договор\r\n"
           "DESCRIPTION:Первая строка\\nВторая строка\r\nEND:VEVENT")
    event, = parse_events(raw)
    assert event.summary == "Смета, счёт; и договор"
    assert event.description == "Первая строка\nВторая строка"


def test_an_all_day_event_is_marked_as_such():
    raw = ("BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Отпуск\r\n"
           "DTSTART;VALUE=DATE:20261012\r\nDTEND;VALUE=DATE:20261013\r\nEND:VEVENT")
    event, = parse_events(raw)
    assert event.all_day and event.start.hour == 0


def test_an_event_without_an_end_still_has_one():
    """Иначе встреча без DTEND выпадала бы из любой проверки пересечений."""
    raw = "BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Звонок\r\nDTSTART:20260922T120000Z\r\nEND:VEVENT"
    event, = parse_events(raw)
    assert event.end - event.start == datetime.timedelta(hours=1)


def test_duration_replaces_a_missing_end():
    raw = ("BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Встреча\r\nDTSTART:20260922T120000Z\r\n"
           "DURATION:PT90M\r\nEND:VEVENT")
    event, = parse_events(raw)
    assert event.end - event.start == datetime.timedelta(minutes=90)


@pytest.mark.parametrize("value,expected", [
    ("PT1H", datetime.timedelta(hours=1)),
    ("P2D", datetime.timedelta(days=2)),
    ("PT15M", datetime.timedelta(minutes=15)),
    ("чепуха", datetime.timedelta(hours=1)),
])
def test_durations_are_read_or_guessed_safely(value, expected):
    assert parse_duration(value) == expected


def test_an_unreadable_event_is_skipped_not_invented():
    """Лучше не показать встречу, чем показать выдуманную."""
    raw = "BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Битое\r\nDTSTART:не дата\r\nEND:VEVENT"
    assert parse_events(raw) == []


def test_attendees_are_read_by_name_when_there_is_one():
    raw = ("BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Планёрка\r\nDTSTART:20260922T120000Z\r\n"
           "ATTENDEE;CN=Анна Ковалёва:mailto:anna@example.com\r\n"
           "ATTENDEE:mailto:sergey@example.com\r\nEND:VEVENT")
    event, = parse_events(raw)
    assert event.attendees == ["Анна Ковалёва", "sergey@example.com"]


def test_a_written_event_can_be_read_back():
    """Круг замкнулся: что записали, то и прочитали."""
    start = datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK)
    uid, body = build_event("Смета", start, end=start + datetime.timedelta(hours=2),
                            location="Офис", description="Взять распечатку")

    event, = parse_events(body)
    assert event.uid == uid
    assert event.start == start and event.end == start + datetime.timedelta(hours=2)
    assert event.summary == "Смета" and event.location == "Офис"


def test_the_clock_shows_the_hour_the_owner_agreed_on():
    """Живой прогон: встреча на 15:00 читалась как 12:00.

    Момент времени при этом был верный — ошибку видно только на часах,
    поэтому сравнивать моменты тут недостаточно.
    """
    start = datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK)
    _, body = build_event("Смета", start)

    event, = parse_events(body, tz=MSK)

    assert "DTSTART:20260922T120000Z" in body    # в файле — честный UTC
    assert f"{event.start:%H:%M}" == "15:00"     # на часах — то, о чём договорились



def test_commas_in_a_title_do_not_split_the_file():
    start = datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK)
    _, body = build_event("Смета, счёт и договор", start)
    event, = parse_events(body)
    assert event.summary == "Смета, счёт и договор"


# -- CalDAV ---------------------------------------------------------------
CALENDAR_LIST = """<?xml version='1.0' encoding='utf-8'?>
<D:multistatus xmlns:D="DAV:">
<D:response><D:href>/calendars/kirill%40yandex.ru/</D:href>
  <D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop>
  <D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
<D:response><D:href>/calendars/kirill%40yandex.ru/events-1/</D:href>
  <D:propstat><D:prop><D:displayname>Мои события</D:displayname>
  <D:resourcetype><C:calendar xmlns:C="urn:ietf:params:xml:ns:caldav"/>
  <D:collection/></D:resourcetype>
  <C:supported-calendar-component-set xmlns:C="urn:ietf:params:xml:ns:caldav">
  <C:comp name="VEVENT"/></C:supported-calendar-component-set>
  </D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
<D:response><D:href>/calendars/kirill%40yandex.ru/todos-1/</D:href>
  <D:propstat><D:prop><D:displayname>Не забыть</D:displayname>
  <D:resourcetype><C:calendar xmlns:C="urn:ietf:params:xml:ns:caldav"/>
  <D:collection/></D:resourcetype>
  <C:supported-calendar-component-set xmlns:C="urn:ietf:params:xml:ns:caldav">
  <C:comp name="VTODO"/></C:supported-calendar-component-set>
  </D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
</D:multistatus>"""


def events_reply(ical):
    return ("<?xml version='1.0' encoding='utf-8'?>"
            '<D:multistatus xmlns:D="DAV:"><D:response>'
            "<D:href>/calendars/kirill%40yandex.ru/events-1/a.ics</D:href>"
            '<D:propstat><D:prop><C:calendar-data '
            'xmlns:C="urn:ietf:params:xml:ns:caldav">' + ical +
            "</C:calendar-data></D:prop></D:propstat></D:response></D:multistatus>")


class FakeHTTP:
    """Столько от httpx.Client, сколько использует CalDAV."""

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def request(self, method, url, content=None, headers=None):
        self.calls.append((method, url, (content or b"").decode("utf-8")))
        return self.replies.pop(0)

    def put(self, url, content=None, headers=None):
        self.calls.append(("PUT", url, content.decode("utf-8")))
        return self.replies.pop(0)


class Reply:
    def __init__(self, text="", status_code=207):
        self.text = text
        self.status_code = status_code


@pytest.fixture
def caldav():
    def build(replies):
        http = FakeHTTP(list(replies))
        client = CalDAV(ACCOUNT, settings(), client=http)
        client.http = http
        return client
    return build


def test_only_event_calendars_are_read(caldav):
    """Список задач «Не забыть» — тоже календарь, но встреч там нет."""
    client = caldav([Reply(CALENDAR_LIST)])
    assert [(c.name, c.kind) for c in client.collections()] == [
        ("Мои события", "VEVENT"), ("Не забыть", "VTODO")]


def test_events_come_back_sorted_and_labelled(caldav):
    client = caldav([Reply(CALENDAR_LIST), Reply(events_reply(YANDEX))])

    events = client.events(datetime.datetime(2026, 9, 21, tzinfo=MSK),
                           datetime.datetime(2026, 9, 30, tzinfo=MSK))

    assert [e.summary for e in events] == ["Созвон с подрядчиком"]
    assert events[0].calendar == "Мои события" and events[0].account == "yandex"


def test_a_cancelled_event_is_not_shown(caldav):
    cancelled = YANDEX.replace("LOCATION:Zoom", "STATUS:CANCELLED")
    client = caldav([Reply(CALENDAR_LIST), Reply(events_reply(cancelled))])

    assert client.events(datetime.datetime(2026, 9, 21, tzinfo=MSK),
                         datetime.datetime(2026, 9, 30, tzinfo=MSK)) == []


def test_the_window_is_sent_in_utc(caldav):
    client = caldav([Reply(CALENDAR_LIST), Reply(events_reply(YANDEX))])
    client.events(datetime.datetime(2026, 9, 21, 12, 0, tzinfo=MSK),
                  datetime.datetime(2026, 9, 30, tzinfo=MSK))

    body = client.http.calls[-1][2]
    assert 'start="20260921T090000Z"' in body      # Москва на три часа впереди


def test_a_wrong_password_says_so_plainly(caldav):
    client = caldav([Reply("", status_code=401)])
    with pytest.raises(ProviderError, match="логин или пароль"):
        client.collections()


def test_writing_a_meeting_lands_in_the_event_calendar(caldav):
    client = caldav([Reply(CALENDAR_LIST), Reply("", status_code=201)])
    start = datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK)

    result = client.create("Смета", start)

    assert result["calendar"] == "Мои события"
    method, url, body = client.http.calls[-1]
    assert method == "PUT" and "/events-1/" in url
    assert "SUMMARY:Смета" in body


def test_a_refused_write_is_reported_not_swallowed(caldav):
    client = caldav([Reply(CALENDAR_LIST), Reply("", status_code=507)])
    with pytest.raises(ProviderError, match="отклонена"):
        client.create("Смета", datetime.datetime(2026, 9, 22, 15, 0, tzinfo=MSK))


# -- действие --------------------------------------------------------------
class Action:
    def __init__(self, **parameters):
        self.parameters = parameters
        self.type = "create.calendar.event"


def test_an_event_without_a_title_is_refused():
    provider = CalendarActionProvider(settings())
    with pytest.raises(ProviderError, match="название"):
        provider.validate(Action(start=1790000000))


def test_an_event_without_a_time_is_refused():
    provider = CalendarActionProvider(settings())
    with pytest.raises(ProviderError, match="время"):
        provider.validate(Action(summary="Созвон"))


def test_the_calendar_is_not_used_when_it_is_not_set_up():
    provider = CalendarActionProvider(CalendarConfig(accounts=()))
    with pytest.raises(ProviderError, match="не настроен"):
        provider.validate(Action(summary="Созвон", start=1790000000))


def test_an_hour_is_assumed_when_no_end_is_given():
    written = {}

    class Stub:
        def create(self, summary, start, **options):
            written.update(summary=summary, start=start, **options)
            return {"uid": "u", "calendar": "Мои события"}

    provider = CalendarActionProvider(settings(), factory=lambda account: Stub())
    provider.execute(Action(summary="Созвон", start="2026-09-22T15:00:00"))

    assert written["end"] - written["start"] == datetime.timedelta(hours=1)


def test_an_unreadable_time_is_refused_clearly():
    provider = CalendarActionProvider(settings(), factory=lambda account: None)
    with pytest.raises(ProviderError, match="не понимаю время"):
        provider.execute(Action(summary="Созвон", start="когда-нибудь"))
