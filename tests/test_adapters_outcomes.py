import tempfile
import unittest
from pathlib import Path

from spicecore.adapters import DeliveryLedger, RecordingAdapter
from spicecore.core import Store, load_personas
from spicecore.outcomes import ingest_batch, ingest_outcome

ROOT = Path(__file__).resolve().parents[1]


class AdapterOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'ledger.sqlite')
        self.person = load_personas(ROOT / 'personas')[0]
        self.cid = self.store.propose(self.person, 'test', 'still', 'TikTok', 'profile')
        self.store.review(self.cid, 'approved', 'owner')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_delivery_requires_live_scoped_receipt_and_is_idempotent(self):
        ledger = DeliveryLedger(Path(self.tmp.name) / 'deliveries.sqlite')
        adapter = RecordingAdapter()
        request = {'key': 'k1', 'account': 'acct', 'action': 'publish',
                   'candidate_id': self.cid}
        dry = {'authorized': True, 'execute': False, 'dry_run': True,
               'receipt_id': 'r0', 'key': 'k1', 'account': 'acct', 'action': 'publish'}
        self.assertFalse(ledger.deliver(adapter, request, dry)['delivered'])
        self.assertEqual(adapter.calls, [])

        live = dict(dry, dry_run=False, receipt_id='r1')
        first = ledger.deliver(adapter, request, live)
        second = ledger.deliver(adapter, request, live)
        self.assertTrue(first['delivered'])
        self.assertEqual(first, second)
        self.assertEqual(len(adapter.calls), 1)

    def test_delivery_rejects_scope_mismatch(self):
        ledger = DeliveryLedger(Path(self.tmp.name) / 'deliveries.sqlite')
        request = {'key': 'k1', 'account': 'acct', 'action': 'publish'}
        receipt = {'authorized': True, 'execute': False, 'dry_run': False,
                   'receipt_id': 'r1', 'key': 'other', 'account': 'acct', 'action': 'publish'}
        with self.assertRaises(PermissionError):
            ledger.deliver(RecordingAdapter(), request, receipt)

    def test_outcomes_require_published_candidate_and_are_idempotent(self):
        event = {'candidate_id': self.cid, 'kind': 'click', 'external_id': 'evt-1',
                 'source': 'tiktok', 'amount_cents': 0}
        with self.assertRaises(ValueError):
            ingest_outcome(self.store, event)
        self.store.publish(self.cid, 'https://example.invalid/post/1', external_id='post-1')
        one = ingest_outcome(self.store, event)
        two = ingest_outcome(self.store, event)
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(self.store.stats([self.person])[0]['clicks'], 1)

    def test_monetary_outcomes_feed_net_results(self):
        self.store.publish(self.cid, 'https://example.invalid/post/1', external_id='post-1')
        ingest_batch(self.store, [
            {'candidate_id': self.cid, 'kind': 'purchase', 'external_id': 'sale-1',
             'source': 'shop', 'amount_cents': 5000},
            {'candidate_id': self.cid, 'kind': 'distribution_cost', 'external_id': 'cost-1',
             'source': 'ads', 'amount_cents': 700},
        ])
        stats = self.store.stats([self.person])[0]
        self.assertEqual(stats['revenue_cents'], 5000)
        self.assertEqual(stats['net_cents'], 4300)


if __name__ == '__main__':
    unittest.main()
