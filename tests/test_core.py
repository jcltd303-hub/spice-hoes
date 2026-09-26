import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas


ROOT = Path(__file__).resolve().parents[1]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'test.sqlite')
        self.people = load_personas(ROOT / 'personas')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def candidate(self):
        return self.store.propose(self.people[0], 'studio', 'still', 'social', 'set',
                                  'assets/example.png', 'prompt', 'test-model', '17', 100)

    def test_five_original_adults_with_version_hashes(self):
        self.assertEqual({p['type'] for p in self.people}, {'Scary', 'Sporty', 'Baby', 'Ginger', 'Posh'})
        self.assertTrue(all(p['age'] >= 18 and p['fictional'] and len(p['version']) == 64 for p in self.people))

    def test_review_and_publication_gate(self):
        cid = self.candidate()
        with self.assertRaises(ValueError):
            self.store.publish(cid, 'https://example.org/post')
        self.store.review(cid, 'rejected', 'operator')
        with self.assertRaises(ValueError):
            self.store.review(cid, 'approved', 'operator')
        with self.assertRaises(ValueError):
            self.store.publish(cid, 'https://example.org/post')
        new_id = self.candidate()
        self.store.review(new_id, 'approved', 'operator')
        self.store.publish(new_id, 'https://example.org/post')
        self.assertEqual(self.store.candidate(new_id)['status'], 'published')

    def test_duplicate_purchase_is_idempotent_and_net_is_correct(self):
        cid = self.candidate()
        self.store.review(cid, 'approved', 'operator')
        self.store.publish(cid, 'https://example.org/post')
        first = self.store.record_outcome(cid, 'purchase', 900, 'payment-1')
        second = self.store.record_outcome(cid, 'purchase', 900, 'payment-1')
        self.assertEqual(first['id'], second['id'])
        with self.assertRaises(ValueError):
            self.store.record_outcome(cid, 'purchase', 1800, 'payment-1')
        self.store.record_outcome(cid, 'refund', 250, 'refund-1')
        self.store.record_outcome(cid, 'distribution_cost', 50, 'ad-1')
        stats = next(s for s in self.store.stats(self.people) if s['persona_id'] == self.people[0]['id'])
        self.assertEqual(stats['net_cents'], 500)
        self.assertEqual(stats['revenue_cents'], 900)

    def test_zero_observations_and_clicks_do_not_create_revenue(self):
        cid = self.candidate()
        self.store.review(cid, 'approved', 'operator')
        self.store.publish(cid, 'https://example.org/post')
        self.store.record_outcome(cid, 'click')
        s = next(x for x in self.store.stats(self.people) if x['persona_id'] == self.people[0]['id'])
        self.assertEqual(s['net_cents'], -100)
        self.assertEqual(s['clicks'], 1)


if __name__ == '__main__':
    unittest.main()
