"""Расписание в ядре: кэш, напоминания, устойчивость к обрыву связи."""
import datetime

import pytest

from core.calendarwatch import CalendarWatcher
from core.config import CalDAVAccount, CalendarConfig
from providers.calendar import Event

ACCOUNT = CalDAVAccount(name="yandex", user="kirill@yandex.ru", password="secret",
                        url="https://caldav.yandex.ru")


def settings(**overrides):
    return CalendarConfig(accounts=(ACCOUNT,), **overrides)


@pytest.fixture
def now():
    from core.config import config

    return datetime.datetime.now(config.tz)


def event(start, minutes=60, summary="Созвон", uid=None, all_day=False):
    return Event(uid=uid or f"uid-{summary}-{start:%H%M}", summary=summary,
                 start=start, end=start + datetime.timedelta(minutes=minutes),
                 all_day=all_day, calendar="Мои события", account="yandex")


class FakeClient:
    account = ACCOUNT

    def __init__(self, events=(), fails=False):
        self._events = list(events)
        self.fails = fails

    def events(self, start, end):
        if self.fails:
            raise OSError("сеть недоступна")
        return [e for e in self._events if e.start < end and e.end > start]


class Stub:
    """Наблюдателю от ядра нужны только шина и уведомления."""

    def __init__(self, bus):
        from core.notifications import NotificationEngine

        self.bus = bus
        self.notifications = NotificationEngine(bus)


@pytest.fixture
def core(bus):
    return Stub(bus)


@pytest.fixture
def watcher(core):
    def build(events=(), cfg=None, clients=None):
        return CalendarWatcher(core, cfg or settings(),
                               clients=clients or [FakeClient(events)])
    return build


def test_the_schedule_is_read_once_and_answered_from_memory(watcher, now):
    """CalDAV — секунды по сети, а расписание спрашивают при каждом ответе."""
    client = FakeClient([event(now + datetime.timedelta(hours=2))])
    watch = watcher(clients=[client])
    watch.refresh()

    calls_before = client._events
    assert len(watch.upcoming()) == 1
    assert len(watch.upcoming()) == 1
    assert client._events is calls_before      # в сеть больше не ходили


def test_a_meeting_in_progress_is_still_ahead(watcher, now):
    """Она ещё не кончилась — значит владельцу про неё важнее всего."""
    watch = watcher([event(now - datetime.timedelta(minutes=10))])
    watch.refresh()
    assert len(watch.upcoming()) == 1


def test_a_finished_meeting_is_not_ahead(watcher, now):
    watch = watcher([event(now - datetime.timedelta(hours=3))])
    watch.refresh()
    assert watch.upcoming() == []


def test_a_broken_connection_does_not_erase_the_schedule(watcher, now):
    """«Встреч нет» и «не смог посмотреть» — разные вещи, и путать их опасно."""
    client = FakeClient([event(now + datetime.timedelta(hours=2))])
    watch = watcher(clients=[client])
    watch.refresh()

    client.fails = True
    report = watch.refresh()

    assert len(watch.upcoming()) == 1
    assert report["errors"] and "сеть недоступна" in report["errors"][0]


def test_one_broken_account_does_not_hide_the_other(watcher, now):
    watch = watcher(clients=[FakeClient(fails=True),
                             FakeClient([event(now + datetime.timedelta(hours=1))])])
    report = watch.refresh()

    assert len(watch.upcoming()) == 1 and len(report["errors"]) == 1


def test_busy_time_is_reported(watcher, now):
    start = now + datetime.timedelta(hours=2)
    watch = watcher([event(start)])
    watch.refresh()

    assert watch.busy_at(start + datetime.timedelta(minutes=30),
                         start + datetime.timedelta(minutes=90))
    assert not watch.busy_at(start + datetime.timedelta(hours=2),
                            start + datetime.timedelta(hours=3))


# -- напоминания -----------------------------------------------------------
def notifications(core):
    return [n for n in core.notifications.history(limit=20)
            if n.get("type") == "calendar.reminder"]


def test_a_meeting_is_announced_before_it_starts(watcher, core, now):
    watch = watcher([event(now + datetime.timedelta(minutes=8), summary="Смета")])
    watch.refresh()

    assert len(watch.check_reminders()) == 1
    core.bus.drain()
    assert any("Смета" in n["title"] for n in notifications(core))


def test_the_same_meeting_is_not_announced_twice(watcher, core, now):
    """Иначе каждая минута фонового цикла давала бы новое напоминание."""
    watch = watcher([event(now + datetime.timedelta(minutes=8))])
    watch.refresh()

    assert len(watch.check_reminders()) == 1
    assert watch.check_reminders() == []


def test_each_threshold_speaks_once(watcher, core, now):
    """За час и за десять минут — это два разных повода, но каждый один раз."""
    watch = watcher([event(now + datetime.timedelta(minutes=50))],
                    cfg=settings(remind_minutes=("60", "10")))
    watch.refresh()

    assert len(watch.check_reminders()) == 1      # сработал порог «за час»
    assert watch.check_reminders() == []


def test_thresholds_are_numbers_in_falling_order_however_they_were_given():
    """Из окружения они приходят строками, а сравниваются с минутами до встречи."""
    assert settings(remind_minutes=("10", "60", "мусор", "0")).remind_minutes == (60, 10)


def test_a_distant_meeting_stays_quiet(watcher, core, now):
    watch = watcher([event(now + datetime.timedelta(hours=9))])
    watch.refresh()
    assert watch.check_reminders() == []


def test_an_all_day_event_does_not_ring(watcher, core, now):
    """«Отпуск» не начинается в 9:00 — напоминать за десять минут бессмысленно."""
    watch = watcher([event(now + datetime.timedelta(minutes=5), all_day=True)])
    watch.refresh()
    assert watch.check_reminders() == []


def test_reminders_are_off_when_nothing_is_configured(watcher, core, now):
    watch = watcher([event(now + datetime.timedelta(minutes=5))],
                    cfg=settings(remind_minutes=()))
    watch.refresh()
    assert watch.check_reminders() == []
