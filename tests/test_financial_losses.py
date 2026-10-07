import tempfile
import unittest
from pathlib import Path

from spicecore.autonomy import AutonomyEngine
from spicecore.core import Store, load_personas


class FinancialLossTests(unittest.TestCase):
    def test_confirmed_chargebacks_and_fee_credits_affect_net_not_gross(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / "ledger.sqlite")
            people = load_personas(Path(__file__).resolve().parents[1] / "personas")
            person = people[0]
            cid = store.propose(person, "style", "still", "instagram", "PDF", cost_cents=10)
            store.review(cid, "approved", "owner")
            store.publish(cid, "https://instagram.com/p/real-shortcode")
            store.record_outcome(cid, "purchase", 1000, "sale")
            store.record_outcome(cid, "commerce_cost", 40, "fee")
            store.record_outcome(cid, "chargeback", 500, "dispute")
            store.record_outcome(cid, "chargeback_reversal", 200, "recovered")
            store.record_outcome(cid, "commerce_cost_reversal", 10, "fee-credit")
            stats = store.stats(people)[0]
            self.assertEqual(stats["revenue_cents"], 1000)
            self.assertEqual(stats["refund_cents"], 0)
            self.assertEqual(stats["chargeback_cents"], 500)
            self.assertEqual(stats["net_cents"], 660)
            autonomy = AutonomyEngine(store, people, None, None)
            self.assertEqual(autonomy._candidate_reward_cents(cid), 660)
            store.close()
