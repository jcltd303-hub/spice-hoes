import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.offers import OfferRegistry

ROOT = Path(__file__).resolve().parents[1]


class OfferAttributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "offers.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.registry = OfferRegistry(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def published_candidate(self, cost_cents=50):
        cid = self.store.propose(
            self.people[0],
            "travel",
            "still",
            "TikTok",
            "affiliate",
            asset_uri="data/item.png",
            prompt="test",
            model="fake",
            seed="1",
            cost_cents=cost_cents,
        )
        self.store.review(cid, "approved", "operator")
        self.store.publish(cid, "https://example.org/post")
        return cid

    def test_tracked_offer_attribution_updates_net_economics_idempotently(self):
        offer = self.registry.create(
            "Travel Tote Affiliate",
            "affiliate",
            expected_payout_cents=900,
            variable_cost_cents=100,
        )
        cid = self.published_candidate(cost_cents=50)
        link = self.registry.register_candidate(
            cid,
            offer["id"],
            "https://shop.example/item?campaign=fall",
        )
        self.assertIn("spice_ref=", link["tracked_url"])
        self.assertIn("campaign=fall", link["tracked_url"])

        click1 = self.registry.ingest(
            link["tracking_token"], "click", "click-1"
        )
        click2 = self.registry.ingest(
            link["tracking_token"], "click", "click-1"
        )
        self.assertEqual(click1["audit_event_id"], click2["audit_event_id"])

        purchase = self.registry.ingest(
            link["tracking_token"], "purchase", "order-1", amount_cents=900
        )
        self.assertEqual(purchase["amount_cents"], 900)
        self.assertIsNotNone(purchase["commerce_cost_event_id"])

        self.registry.ingest(
            link["tracking_token"], "refund", "refund-1", amount_cents=200
        )

        perf = self.registry.performance(offer["id"])
        self.assertEqual(perf["clicks"], 1)
        self.assertEqual(perf["purchases"], 1)
        self.assertEqual(perf["revenue_cents"], 900)
        self.assertEqual(perf["refund_cents"], 200)
        self.assertEqual(perf["commerce_cost_cents"], 100)
        self.assertEqual(perf["generation_cost_cents"], 50)
        self.assertEqual(perf["net_cents"], 550)
        self.assertEqual(perf["expected_unit_margin_cents"], 800)

        stats = next(
            s for s in self.store.stats(self.people)
            if s["persona_id"] == self.people[0]["id"]
        )
        self.assertEqual(stats["commerce_cost_cents"], 100)
        self.assertEqual(stats["net_cents"], 550)

    def test_inactive_offer_cannot_be_newly_registered(self):
        offer = self.registry.create("Inactive", "other")
        self.registry.set_active(offer["id"], False)
        cid = self.published_candidate()
        with self.assertRaises(ValueError):
            self.registry.register_candidate(
                cid, offer["id"], "https://example.org/item"
            )

    def test_non_usd_offer_is_rejected_until_multi_currency_exists(self):
        with self.assertRaises(ValueError):
            self.registry.create("EUR offer", "affiliate", currency="EUR")


if __name__ == "__main__":
    unittest.main()
