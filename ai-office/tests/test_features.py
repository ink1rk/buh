import unittest
import uuid
from decimal import Decimal

from aioffice.calendars import credential_flags, deliver_event, google_body, status_lines, yandex_collection, yandex_ics
from aioffice.costs import budget_blocks, budget_text, reconcile
from aioffice.files import VOICE_REPLY, accept_file, describe_incoming, file_allowed, transcribe
from aioffice.integrations import approval_effect, plan_external
from aioffice.job import job_template, should_submit, specialist_job, specialist_prompt
from aioffice.policy import callback_actor, normalize_timezone, payload_hash


class FeatureTests(unittest.TestCase):
    def test_reconcile_does_not_confirm_estimate_or_litellm(self):
        row = reconcile(estimated_usd='1.25', usage_api_status='feature_unavailable', litellm_spend_usd='0')
        self.assertFalse(row['actual_confirmed'])
        self.assertIsNone(row['dashboard_usd'])
        confirmed = reconcile(estimated_usd='1', usage_api_status='dashboard_confirmed', litellm_spend_usd='0', dashboard_usd='0.40')
        self.assertTrue(confirmed['actual_confirmed'])
        self.assertEqual(confirmed['dashboard_usd'], Decimal('0.40'))

    def test_budget_text_names_dashboard(self):
        text = budget_text(estimated=0, reserve_week=0, litellm_spend=None, usage_api_status='feature_unavailable')
        self.assertIn('Cursor Dashboard', text)
        self.assertIn('недоступен', text)

    def test_budget_blocks_on_the_41st_half_dollar(self):
        self.assertFalse(budget_blocks(Decimal('20.00') - Decimal('0.50'), 0))
        self.assertTrue(budget_blocks(Decimal('20.00'), 0))

    def test_callback_rejects_group_and_stranger(self):
        token = str(uuid.uuid4())
        query = {'callback_query': {'data': 'a:' + token, 'from': {'id': 7, 'is_bot': False}, 'message': {'chat': {'id': 7, 'type': 'group'}}}}
        self.assertIsNone(callback_actor(query, {7}))
        stranger = {'callback_query': {'data': 'a:' + token, 'from': {'id': 8, 'is_bot': False}, 'message': {'chat': {'id': 8, 'type': 'private'}}}}
        self.assertIsNone(callback_actor(stranger, {7}))
        owner = {'callback_query': {'data': 'r:' + token, 'from': {'id': 7, 'is_bot': False}, 'message': {'chat': {'id': 7, 'type': 'private'}}}}
        self.assertEqual(callback_actor(owner, {7}), 7)

    def test_callback_rejects_overlong_or_non_uuid(self):
        bad = {'callback_query': {'data': 'a:' + 'x' * 70, 'from': {'id': 7, 'is_bot': False}, 'message': {'chat': {'id': 7, 'type': 'private'}}}}
        self.assertIsNone(callback_actor(bad, {7}))

    def test_approval_never_calls_out_without_provider(self):
        effect = approval_effect(allowed=True, decision='approve', provider='', kind='calendar')
        self.assertFalse(effect['outbound'])
        self.assertEqual(effect['reason'], 'provider_not_configured')
        named = approval_effect(allowed=True, decision='approve', provider='caldav', kind='email')
        self.assertFalse(named['outbound'])
        self.assertEqual(named['reason'], 'writer_not_shipped')
        self.assertFalse(plan_external('calendar', '')['outbound'])

    def test_reject_does_not_call_out(self):
        effect = approval_effect(allowed=True, decision='reject', provider='caldav', kind='calendar')
        self.assertEqual(effect['task_state'], 'cancelled')
        self.assertFalse(effect['outbound'])

    def test_expired_approval_is_denied(self):
        effect = approval_effect(allowed=False, decision='approve', provider='', kind='calendar')
        self.assertIsNone(effect['task_state'])
        self.assertEqual(effect['reason'], 'denied')

    def test_file_limits(self):
        self.assertTrue(file_allowed('voice', 'audio/ogg', 100))
        self.assertFalse(file_allowed('document', 'application/x-executable', 100))
        self.assertFalse(file_allowed('photo', 'image/jpeg', 2_000_001))
        digest = accept_file('photo', 'image/jpeg', 3, b'abc')
        self.assertEqual(len(digest), 64)
        with self.assertRaises(ValueError):
            accept_file('voice', 'audio/ogg', 2, b'abcd')

    def test_voice_is_not_sent_to_a_transcriber(self):
        message = {'voice': {'file_id': 'f', 'file_unique_id': 'u', 'mime_type': 'audio/ogg', 'file_size': 4}}
        self.assertEqual(describe_incoming(message)[0], 'voice')
        self.assertIn('не отправляется', VOICE_REPLY)

        def boom(command, data):
            raise AssertionError('transcriber was called')

        self.assertIsNone(transcribe('voice', b'abcd', '', boom))

    def test_smoke_job_still_accepts_zero_digest(self):
        job = job_template(uuid.uuid4(), image='example@sha256:' + '0' * 64, secret_name='worker')
        self.assertFalse(job['spec']['template']['spec']['automountServiceAccountToken'])
        names = [item['name'] for item in job['spec']['template']['spec']['containers'][0]['env']]
        self.assertNotIn('HTTP_PROXY', names)

    def test_specialist_job_rejects_placeholder_shell_and_hides_output(self):
        image = 'example@sha256:' + 'ab' * 32
        with self.assertRaises(ValueError):
            specialist_job(uuid.uuid4(), image='example@sha256:' + '0' * 64, secret_name='worker', profile='researcher')
        with self.assertRaises(ValueError):
            specialist_job(uuid.uuid4(), image=image, secret_name='worker', profile='root')
        with self.assertRaises(ValueError):
            specialist_job('x; whoami', image=image, secret_name='worker', profile='researcher')
        job = specialist_job(uuid.uuid4(), image=image, secret_name='worker', profile='planner')
        env = job['spec']['template']['spec']['containers'][0]['env']
        self.assertEqual(job['spec']['template']['spec']['containers'][0]['command'], ['python', '-m', 'aioffice.specialist'])
        self.assertNotIn('sh', job['spec']['template']['spec']['containers'][0]['command'])
        self.assertTrue(all(item['name'] != 'EXECUTION_TOKEN' or 'valueFrom' in item for item in env))
        self.assertFalse(any(item['name'] in ('PROMPT', 'MODEL_OUTPUT', 'CURSOR_API_KEY') for item in env))
        self.assertFalse(job['spec']['template']['spec']['automountServiceAccountToken'])
        self.assertEqual(job['spec']['backoffLimit'], 0)

    def test_submit_is_idempotent_by_job_name(self):
        task = uuid.uuid4()
        name = 'sp-' + str(task).replace('-', '')
        self.assertFalse(should_submit([name], task))
        self.assertTrue(should_submit([], task))

    def test_prompt_denies_tools(self):
        text = specialist_prompt('researcher', 'сравни два абзаца')
        self.assertIn('нет shell', text)
        self.assertIn('researcher', text)

    def test_payload_hash_stable_for_approval(self):
        self.assertEqual(payload_hash({'kind': 'email', 'to': 'a'}), payload_hash({'to': 'a', 'kind': 'email'}))

    def test_plus_three_is_moscow(self):
        self.assertEqual(normalize_timezone('+3'), 'Europe/Moscow')
        self.assertEqual(normalize_timezone(''), 'Europe/Moscow')
        self.assertEqual(normalize_timezone('Europe/Moscow'), 'Europe/Moscow')

    def test_calendar_without_credentials_does_not_call_out(self):
        effect = approval_effect(allowed=True, decision='approve', provider='google', kind='calendar', credentials=False)
        self.assertFalse(effect['outbound'])
        self.assertEqual(effect['reason'], 'credentials_missing')
        yandex = approval_effect(allowed=True, decision='approve', provider='yandex', kind='calendar', credentials=False)
        self.assertFalse(yandex['outbound'])
        ready = approval_effect(allowed=True, decision='approve', provider='google', kind='calendar', credentials=True)
        self.assertTrue(ready['outbound'])
        self.assertEqual(ready['reason'], 'ready')
        self.assertFalse(credential_flags({})['google'])
        self.assertFalse(credential_flags({})['yandex'])

    def test_calendar_event_has_no_attendees(self):
        body = google_body('Встреча', '2030-01-01T12:00', 'Europe/Moscow', 'abc')
        self.assertNotIn('attendees', body)
        self.assertEqual(body['start']['timeZone'], 'Europe/Moscow')
        self.assertEqual(body['start']['dateTime'], '2030-01-01T12:00:00')
        ics = yandex_ics('Встреча', '2030-01-01T12:00', 'Europe/Moscow', 'abc')
        self.assertNotIn('ATTENDEE', ics)
        self.assertIn('TZID:Europe/Moscow', ics)
        self.assertIn('SUMMARY:Встреча', ics)
        text = status_lines('Europe/Moscow', ('google', 'yandex'), {})
        self.assertIn('UTC+3', text)
        self.assertIn('Google', text)
        self.assertIn('Яндекс', text)

    def test_yandex_href_rejects_embedded_password(self):
        with self.assertRaises(Exception):
            yandex_collection({'YANDEX_CALDAV_HREF': 'https://user:secret@caldav.yandex.ru/calendars/a/'})
        self.assertTrue(yandex_collection({'YANDEX_CALDAV_USER': 'owner@yandex.ru'}).startswith('https://caldav.yandex.ru/calendars/'))

    def test_google_write_is_idempotent_and_stays_on_google(self):
        seen = []

        class Response:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            seen.append((request.full_url, request.get_method(), request.data))
            if request.full_url.startswith('https://www.googleapis.com/calendar/v3/calendars/primary/events?'):
                return Response(b'{"items":[{"id":"existing"}]}')
            raise AssertionError('second call')

        result = deliver_event('google', 'Встреча', '2030-01-01T12:00', 'Europe/Moscow', 'abc',
                                {'GOOGLE_CALENDAR_TOKEN': 'token-value'}, opener)
        self.assertEqual(result['id'], 'existing')
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0][0].startswith('https://www.googleapis.com/'))
        self.assertNotIn('token-value', seen[0][0])


if __name__ == '__main__':
    unittest.main()
