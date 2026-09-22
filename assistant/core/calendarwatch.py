#!/usr/bin/env python3
"""Расписание владельца: кэш ближайших встреч и напоминания о них.

CalDAV — сетевой запрос на секунды, а расписание спрашивают часто: при каждом
ответе, в панели, в подсказках. Поэтому окно ближайших дней держится в памяти
и обновляется фоном, а спрашивающий всегда получает ответ сразу.
"""
import datetime
import json
import threading
import time

from .config import config
from .events import E

REMINDED_KEY = "calendar_reminded"
# Напоминание живёт недолго: помнить, что предупредили о встрече месяц назад,
# незачем, а список не должен расти вечно.
FORGET_AFTER = 3 * 86400


class CalendarWatcher:
    def __init__(self, core, cfg=None, clients=None):
        self.core = core
        self.cfg = cfg or config.calendar
        self._clients = clients
        self._events = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.last = {"at": None, "events": 0, "errors": []}

    @property
    def clients(self):
        if self._clients is None:
            from providers.calendar import clients

            self._clients = clients(self.cfg)
        return self._clients

    # -- расписание ------------------------------------------------------
    def refresh(self):
        """Забрать окно ближайших дней. Сломанный аккаунт не прячет остальные."""
        now = datetime.datetime.now(config.tz)
        window_end = now + datetime.timedelta(days=self.cfg.horizon_days)
        events, errors = [], []
        for client in self.clients:
            try:
                events.extend(client.events(now - datetime.timedelta(hours=12),
                                            window_end))
            except Exception as e:
                errors.append(f"{client.account.name}: {e}")
        try:
            from .finance_bridge import finance_schedule

            events.extend(finance_schedule(self.cfg.horizon_days))
        except Exception as e:
            errors.append(f"finance: {e}")
        events.sort(key=lambda item: item.start)
        with self._lock:
            # Пустой ответ из-за сетевой ошибки не должен стирать расписание:
            # «встреч нет» и «не смог посмотреть» — разные вещи.
            if events or not errors:
                self._events = events
        self.last = {"at": time.time(), "events": len(events), "errors": errors}
        return self.last

    def upcoming(self, limit=None, within_hours=None):
        """Что впереди. Идущая сейчас встреча тоже впереди — она ещё не кончилась."""
        now = datetime.datetime.now(config.tz)
        edge = (now + datetime.timedelta(hours=within_hours)) if within_hours else None
        with self._lock:
            events = list(self._events)
        ahead = [e for e in events if e.end > now and (edge is None or e.start <= edge)]
        return ahead[:limit] if limit else ahead

    def today(self):
        now = datetime.datetime.now(config.tz)
        end = now.replace(hour=23, minute=59, second=59)
        return [e for e in self.upcoming() if e.start <= end]

    def busy_at(self, start, end):
        """Занято ли время — чтобы не назначить встречу поверх встречи."""
        return [e for e in self.upcoming()
                if e.start < end and e.end > start and not e.all_day]

    # -- напоминания -----------------------------------------------------
    def check_reminders(self):
        """Предупредить о встрече заранее, и только один раз про каждый порог."""
        if not self.cfg.remind_minutes:
            return []
        now = datetime.datetime.now(config.tz)
        seen = self._reminded()
        sent = []
        for event in self.upcoming():
            if event.all_day:
                continue
            minutes_left = (event.start - now).total_seconds() / 60
            for threshold in self.cfg.remind_minutes:
                # Порог сработал, если встреча ближе него, но не ближе
                # следующего: иначе одна встреча дала бы напоминание на каждый.
                if not 0 <= minutes_left <= threshold:
                    continue
                key = f"{event.uid}:{int(event.start.timestamp())}:{threshold}"
                if key in seen:
                    break
                seen[key] = time.time()
                self._notify(event, threshold, minutes_left)
                sent.append(key)
                break
        self._forget_old(seen)
        return sent

    def _notify(self, event, threshold, minutes_left):
        when = f"{event.start:%H:%M}"
        soon = ("начинается" if minutes_left < 2
                else f"через {int(round(minutes_left))} мин")
        body = f"{event.summary} {soon}, в {when}"
        if event.location:
            body += f" · {event.location}"
        self.core.notifications.notify(
            "calendar.reminder", event.summary, body=body,
            severity="high" if threshold <= 15 else "medium",
            metadata={"kind": "calendar", "uid": event.uid, "when": when,
                      "location": event.location, "calendar": event.calendar,
                      "start": event.start.timestamp()})
        self.core.bus.emit(E.CALENDAR_REMINDER,
                           {"uid": event.uid, "summary": event.summary,
                            "start": event.start.timestamp(), "threshold": threshold},
                           source="calendar")

    def _reminded(self):
        from . import db

        try:
            return json.loads(db.setting(REMINDED_KEY) or "{}")
        except (ValueError, TypeError):
            return {}

    def _forget_old(self, seen):
        from . import db

        edge = time.time() - FORGET_AFTER
        fresh = {key: at for key, at in seen.items() if at > edge}
        db.set_setting(REMINDED_KEY, json.dumps(fresh))

    # -- фоновый поток ----------------------------------------------------
    def start(self):
        if self._thread is not None:
            return False
        # Без CalDAV всё равно забираем платежи из финансов: для владельца
        # это одно расписание, а не два приложения.
        if not self.cfg.enabled and not config.finance_api:
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="calendar-watch")
        self._thread.start()
        return True

    def _loop(self):
        self._safe(self.refresh)
        since = time.time()
        # Напоминания проверяются чаще, чем обновляется расписание: минута
        # опоздания в напоминании заметна, а новая встреча — нет.
        while not self._stop.wait(60):
            if time.time() - since >= self.cfg.refresh_seconds:
                self._safe(self.refresh)
                since = time.time()
            self._safe(self.check_reminders)

    def _safe(self, step):
        try:
            return step()
        except Exception as e:
            print(f"calendar {step.__name__} failed: {type(e).__name__}: {e}")
            return None

    def stop(self):
        self._stop.set()
