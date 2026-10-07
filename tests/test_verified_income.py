import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.offers import OfferRegistry

ROOT = Path(__file__).resolve().parents[1]


class VerifiedIncomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "income.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.cid = self.store.propose(self.people[0], "outfit", "still", "instagram",
                                      "guide", cost_cents=50)
        self.store.review(self.cid, "approved", "owner")
        self.store.publish(self.cid, "https://www.instagram.com/p/receipt/")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_expected_payout_is_never_an_observed_purchase(self):
        offers = OfferRegistry(self.store)
        offer = offers.create("Affiliate", "affiliate", expected_payout_cents=99999)
        link = offers.register_candidate(self.cid, offer["id"], "https://shop.example/item")
        with self.assertRaises(ValueError):
            offers.ingest(link["tracking_token"], "purchase", "missing-receipt")
        self.assertFalse(any(e["kind"] == "purchase" for e in self.store.events()))

    def test_unverified_income_does_not_inflate_production_stats(self):
        self.store.record_outcome(self.cid, "purchase", 500000, external_id="stripe:spoof")
        self.store.record_outcome(self.cid, "distribution_cost", 200)
        row = self.store.stats(self.people, verified_revenue_only=True)[0]
        self.assertEqual(row["revenue_cents"], 0)
        self.assertEqual(row["net_cents"], -250)
        self.assertEqual(self.store.stats(self.people)[0]["revenue_cents"], 500000)


if __name__ == "__main__":
    unittest.main()
