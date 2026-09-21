#!/usr/bin/env python3
"""Опрос почтовых ящиков.

Связывает транспорт (`providers/email.py`) с общим конвейером: письмо от
человека становится тем же входящим сообщением, что и сообщение в Telegram —
с контактом, диалогом, обязательствами и подсказками ответов.

Отдельного демона нет: IMAP — это короткий опрос раз в несколько минут, и
ради него заводить ещё один systemd-юнит незачем.
"""
import json
import threading
import time

from .config import config

STATE_KEY = "email_last_uid"


class MailWatcher:
    def __init__(self, core, cfg=None, mailboxes=None):
        self.core = core
        self.cfg = cfg or config.email
        self._mailboxes = mailboxes
        self._stop = threading.Event()
        self._thread = None
        self.last = {"at": None, "new": 0, "skipped": 0, "errors": []}

    @property
    def mailboxes(self):
        if self._mailboxes is None:
            from providers.email import mailboxes as build
            self._mailboxes = build(self.cfg)
        return self._mailboxes

    # -- работа ---------------------------------------------------------
    def poll_once(self):
        """Один проход по всем ящикам. Возвращает, что удалось и что нет."""
        from . import pipeline

        result = {"at": time.time(), "new": 0, "skipped": 0, "duplicates": 0,
                  "stale": 0, "started": [], "skipped_senders": [], "errors": []}
        skipped = {}
        oldest = time.time() - self.cfg.max_age_hours * 3600
        for mailbox in self.mailboxes:
            try:
                letters, state = mailbox.fetch_new(self._state(mailbox))
                self._remember(mailbox, state)
            except Exception as e:
                result["errors"].append(f"{mailbox.account.name}: {e}")
                continue
            if state.get("first"):
                # Первый запуск: прошлое ящика помечено и не разбирается.
                result["started"].append(mailbox.account.address)

            for letter in letters:
                if not letter.get("personal"):
                    # Рассылки не заводят контакт и не ждут ответа: иначе
                    # входящие превратились бы в рекламную ленту. Но отбор не
                    # безошибочен, поэтому отсеянное видно владельцу.
                    result["skipped"] += 1
                    skipped[letter.get("address")] = skipped.get(
                        letter.get("address"), 0) + 1
                    continue
                if not (letter.get("text") or letter.get("subject")):
                    result["skipped"] += 1
                    continue
                if (letter.get("ts") or 0) < oldest:
                    # Письмо месячной давности не ждёт ответа сегодня.
                    result["stale"] += 1
                    continue
                try:
                    ingested = pipeline.ingest_incoming(self.core, letter,
                                                        channel="email")
                except Exception as e:
                    result["errors"].append(f"{letter.get('address')}: {e}")
                    continue
                if ingested.get("duplicate"):
                    result["duplicates"] += 1
                else:
                    result["new"] += 1

        result["skipped_senders"] = [
            {"address": address, "count": count} for address, count
            in sorted(skipped.items(), key=lambda item: -item[1])[:15]]
        self.last = result
        return result

    # -- где остановились -----------------------------------------------
    def _key(self, mailbox):
        return f"{STATE_KEY}:{mailbox.account.name}"

    def _state(self, mailbox):
        from . import db

        try:
            return json.loads(db.setting(self._key(mailbox)) or "{}")
        except (ValueError, TypeError):
            return {}

    def _remember(self, mailbox, state):
        from . import db

        db.set_setting(self._key(mailbox),
                       json.dumps({"uid": state.get("uid", 0),
                                   "uidvalidity": state.get("uidvalidity", 0)}))

    # -- фоновый поток --------------------------------------------------
    def start(self):
        if not self.cfg.enabled or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="mail-watch")
        self._thread.start()
        return True

    def _loop(self):
        # Первый проход с задержкой: на старте ядро ещё поднимает модели.
        while not self._stop.wait(self.cfg.poll_seconds):
            try:
                self.poll_once()
            except Exception as e:
                print("mail poll failed:", e)

    def stop(self):
        self._stop.set()
