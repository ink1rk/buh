import unittest
import uuid
from datetime import UTC, datetime, timedelta

from aioffice.job import job_template
from aioffice.policy import external_write_allowed, parse_due, payload_hash, private_owner


class PolicyTests(unittest.TestCase):
    def update(self, owner=7, chat=7, kind='private', bot=False):
        return {'message': {'from': {'id': owner, 'is_bot': bot}, 'chat': {'id': chat, 'type': kind}}}

    def test_private_owner_allowed(self):
        self.assertEqual(private_owner(self.update(), {7}), 7)

    def test_other_user_rejected(self):
        self.assertIsNone(private_owner(self.update(8, 8), {7}))

    def test_group_rejected_even_for_owner(self):
        self.assertIsNone(private_owner(self.update(kind='group'), {7}))

    def test_mismatched_chat_rejected(self):
        self.assertIsNone(private_owner(self.update(chat=8), {7}))

    def test_bot_rejected(self):
        self.assertIsNone(private_owner(self.update(bot=True), {7}))

    def test_no_timezone_no_reminder(self):
        with self.assertRaises(ValueError):
            parse_due('2030-01-01T12:00', '')

    def test_moscow_conversion(self):
        self.assertEqual(parse_due('2030-01-01T12:00', 'Europe/Moscow'), datetime(2030, 1, 1, 9, tzinfo=UTC))

    def test_ambiguous_dst_rejected(self):
        with self.assertRaises(ValueError):
            parse_due('2030-10-27T02:30', 'Europe/Amsterdam')

    def test_missing_dst_hour_rejected(self):
        with self.assertRaises(ValueError):
            parse_due('2030-03-31T02:30', 'Europe/Amsterdam')

    def test_explicit_offset_allowed(self):
        self.assertEqual(parse_due('2030-10-27T02:30+02:00', 'Europe/Amsterdam'), datetime(2030, 10, 27, 0, 30, tzinfo=UTC))

    def test_past_due_rejected(self):
        with self.assertRaises(ValueError):
            parse_due('2000-01-01T12:00', 'Europe/Moscow')

    def test_payload_hash_is_canonical(self):
        self.assertEqual(payload_hash({'a': 1, 'b': 2}), payload_hash({'b': 2, 'a': 1}))

    def test_approval_without_capability_rejected(self):
        self.assertFalse(external_write_allowed())

    def test_wrong_payload_or_owner_cannot_be_approved(self):
        approval = {'owner_id': 7, 'expires_at': datetime.now(UTC) + timedelta(minutes=1), 'consumed_at': None, 'payload_hash': payload_hash({'x': 1})}
        self.assertFalse(external_write_allowed(capability=True, approval=approval, owner=8, payload={'x': 1}))
        self.assertFalse(external_write_allowed(capability=True, approval=approval, owner=7, payload={'x': 2}))
        approval['consumed_at'] = datetime.now(UTC)
        self.assertFalse(external_write_allowed(capability=True, approval=approval, owner=7, payload={'x': 1}))

    def test_expired_approval_rejected(self):
        approval = {'owner_id': 7, 'expires_at': datetime.now(UTC) - timedelta(seconds=1), 'consumed_at': None, 'payload_hash': payload_hash({'x': 1})}
        self.assertFalse(external_write_allowed(capability=True, approval=approval, owner=7, payload={'x': 1}))

    def test_unpinned_job_rejected(self):
        with self.assertRaises(ValueError):
            job_template(uuid.uuid4(), image='example:latest', secret_name='worker')

    def test_task_cannot_inject_shell(self):
        with self.assertRaises(ValueError):
            job_template('x; whoami', image='example@sha256:' + '0' * 64, secret_name='worker')

    def test_job_has_no_kubernetes_token(self):
        job = job_template(uuid.uuid4(), image='example@sha256:' + '0' * 64, secret_name='worker')
        spec = job['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertTrue(spec['containers'][0]['securityContext']['readOnlyRootFilesystem'])


if __name__ == '__main__':
    unittest.main()

