import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from .db import audit
from .service import process_callback, process_update, schedule_due
from .telegram import Telegram, TelegramError

log = logging.getLogger('aioffice')


def deliver_one(engine, telegram):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT e.* FROM outbox_events e JOIN users u ON u.id=e.owner_id WHERE e.state='pending' AND e.available_at<=now() AND (e.payload->>'category' IS DISTINCT FROM 'reminder' OR NOT u.paused) ORDER BY e.created_at FOR UPDATE OF e SKIP LOCKED LIMIT 1")).mappings().first()
        if not row:
            return False
        conn.execute(text("UPDATE outbox_events SET state='sending',attempts=attempts+1 WHERE id=:id"), {'id': row['id']})
    state, delay = 'sent', 0
    try:
        payload = {'chat_id': row['chat_id'], 'text': row['payload']['text'][:4000]}
        if row['payload'].get('reply_markup'):
            payload['reply_markup'] = row['payload']['reply_markup']
        telegram.call('sendMessage', **payload)
    except TelegramError as exc:
        if exc.code == 429:
            state, delay = 'pending', max(1, min(int(exc.retry_after), 86400))
        elif 400 <= exc.code < 500:
            state = 'failed'
        else:
            # Telegram has no idempotency key for sendMessage. An uncertain
            # network/5xx outcome requires operator review, never blind replay.
            state = 'uncertain'
    with engine.begin() as conn:
        conn.execute(text('UPDATE outbox_events SET state=:s,available_at=:a,sent_at=:t WHERE id=:id'),
                     {'s': state, 'a': datetime.now(UTC) + timedelta(seconds=delay),
                      't': datetime.now(UTC) if state == 'sent' else None, 'id': row['id']})
        audit(conn, row['owner_id'], 'telegram.' + state, str(row['id']))
    return True


class Runtime:
    def __init__(self, engine, settings, stop):
        self.engine, self.settings, self.stop = engine, settings, stop
        self.last_poll = 0.0
        self.leader = False
        self.failed = False

    def run(self):
        if not self.settings.polling:
            return
        telegram = Telegram(self.settings.telegram_token)
        while not self.stop.is_set():
            try:
                with self.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as lock:
                    self.leader = lock.execute(text('SELECT pg_try_advisory_lock(185115002)')).scalar_one()
                    if not self.leader:
                        self.stop.wait(5)
                        continue
                    try:
                        info = telegram.call('getWebhookInfo')
                        if info.get('url'):
                            self.failed = True
                            log.error('Polling refused: webhook is configured')
                            return
                        with self.engine.begin() as conn:
                            conn.execute(text("UPDATE outbox_events SET state='uncertain' WHERE state='sending'"))
                        while not self.stop.is_set():
                            lock.execute(text('SELECT 1'))
                            schedule_due(self.engine)
                            for _ in range(10):
                                if not deliver_one(self.engine, telegram):
                                    break
                            with self.engine.connect() as conn:
                                offset = conn.execute(text('SELECT next_offset FROM poll_state WHERE id=1')).scalar_one()
                            updates = telegram.call('getUpdates', offset=offset, timeout=10, limit=50, allowed_updates=['message', 'callback_query'])
                            for update in updates:
                                if 'callback_query' in update:
                                    ack = process_callback(self.engine, update, self.settings)
                                    query_id = (update.get('callback_query') or {}).get('id')
                                    if query_id:
                                        try:
                                            telegram.call('answerCallbackQuery', callback_query_id=query_id, text=ack[:180])
                                        except TelegramError:
                                            log.warning('Callback acknowledgement failed')
                                else:
                                    process_update(self.engine, update, self.settings, fetch_file=telegram.fetch)
                            self.last_poll = time.monotonic()
                    finally:
                        try:
                            lock.execute(text('SELECT pg_advisory_unlock(185115002)'))
                        finally:
                            self.leader = False
            except TelegramError as exc:
                if exc.code in (401, 409):
                    self.failed = True
                    log.error('Polling stopped; Telegram error code=%d', exc.code)
                    return
                log.warning('Telegram unavailable; code=%d', exc.code)
                self.stop.wait(max(5, min(exc.retry_after, 60)))
            except Exception as exc:
                log.error('Runtime retry; exception_type=%s', type(exc).__name__)
                self.stop.wait(5)

