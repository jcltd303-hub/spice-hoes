import tempfile
import unittest
from spicecore.jobs import JobStore


class JobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(self.tmp.name + '/jobs.db')
    def tearDown(self):
        self.tmp.cleanup()
    def test_duplicate_key_conflict(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'key')
        self.assertEqual(job, self.store.enqueue('image', {'device_id': 'phone'}, 'key'))
        with self.assertRaises(ValueError):
            self.store.enqueue('image', {'device_id': 'other'}, 'key')
    def test_device_lease_and_fencing(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        self.store.enqueue('image', {'device_id': 'phone'}, 'b')
        first = self.store.claim('one', '2026-09-30T00:00:00Z')
        self.assertIsNone(self.store.claim('two', '2026-09-30T00:00:01Z'))
        second = self.store.claim('two', '2026-09-30T00:02:01Z')
        self.assertEqual(job, second['id'])
        with self.assertRaises(ValueError):
            self.store.complete(job, first['lease_token'], {'ok': True})
    def test_late_completion(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        first = self.store.claim('one', '2026-09-30T00:00:00Z')
        self.store.claim('two', '2026-09-30T00:02:01Z')
        result = {'artifact_hash': 'a' * 64}
        receipt = self.store.reconcile_artifact(job, first['lease_token'], result)
        self.assertFalse(receipt['deliver'])
        self.assertEqual(receipt, self.store.reconcile_artifact(job, first['lease_token'], result))
        self.assertIsNone(self.store.claim('three', '2026-09-30T00:05:00Z'))
    def test_deadletter(self):
        self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        for minute in (0, 3, 6):
            self.assertIsNotNone(self.store.claim('one', f'2026-09-30T00:0{minute}:00Z'))
        self.assertIsNone(self.store.claim('one', '2026-09-30T00:09:00Z'))
    def test_renew_and_complete(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        claim = self.store.claim('one', '2026-09-30T00:00:00Z')
        self.store.renew(job, claim['lease_token'], now='2026-09-30T00:01:30Z')
        self.assertIsNone(self.store.claim('two', '2026-09-30T00:02:01Z'))
        receipt = self.store.complete(job, claim['lease_token'], {'ok': True}, now='2026-09-30T00:02:01Z')
        self.assertTrue(receipt['deliver'])
        self.assertFalse(self.store.complete(job, claim['lease_token'], {'ok': True})['deliver'])
    def test_pause_persists(self):
        self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        self.store.set_controls(paused=True)
        reopened = JobStore(self.store.path)
        self.assertIsNone(reopened.claim('one', '2026-09-30T00:00:00Z'))
    def test_reconciliation_does_not_steal_token(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        old = self.store.claim('one', '2026-09-30T00:00:00Z')
        new = self.store.claim('two', '2026-09-30T00:02:01Z')
        self.store.reconcile_artifact(job, old['lease_token'], {'artifact_hash': 'a' * 64})
        self.store.renew(job, new['lease_token'], now='2026-09-30T00:02:30Z')
        with self.assertRaises(ValueError):
            self.store.reconcile_artifact(job, old['lease_token'], {'artifact_hash': 'b' * 64})
    def test_completion_respects_checkpointed_artifact(self):
        job = self.store.enqueue('image', {'device_id': 'phone'}, 'a')
        old = self.store.claim('one', '2026-09-30T00:00:00Z')
        new = self.store.claim('two', '2026-09-30T00:02:01Z')
        self.store.reconcile_artifact(job, old['lease_token'], {'artifact_hash': 'a' * 64})
        with self.assertRaises(ValueError):
            self.store.complete(job, new['lease_token'], {'artifact_hash': 'b' * 64}, now='2026-09-30T00:02:30Z')
        receipt = self.store.complete(job, new['lease_token'], {'artifact_hash': 'a' * 64}, now='2026-09-30T00:02:30Z')
        self.assertTrue(receipt['deliver'])
        self.assertFalse(self.store.complete(job, new['lease_token'], {'artifact_hash': 'a' * 64})['deliver'])
