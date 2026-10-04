import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.gold_digger import dig_report, vein_stats


PERSONA = {"id": "zara_voss", "version": 3, "name": "Zara Voss", "disclosure": "Fictional AI persona"}
GOAL = "fridge drive"


def _publish_candidate(store, theme, impressions, donations_cents):
    cid = store.propose(PERSONA, theme, "post", "nextdoor", "https://example.org/x",
                        prompt="body", model="t", seed="1", cost_cents=0)
    store.review(cid, "approved", "tester")
    store.publish(cid, f"https://nextdoor.example/p/{cid[:8]}")
    for _ in range(impressions):
        store.record_outcome(cid, "impression")
    for _ in range(donations_cents // 500):
        store.record_outcome(cid, "purchase", amount_cents=500)
    return cid


def _setup_store():
    tmp = tempfile.TemporaryDirectory()
    store = Store(Path(tmp.name) / "gold.sqlite")
    cids = {
        "story": _publish_candidate(store, f"{GOAL} [story]", 120, 1500),
        "offer": _publish_candidate(store, f"{GOAL} [offer]", 120, 500),
        "event": _publish_candidate(store, f"{GOAL} [event]", 250, 0),
        "fresh": _publish_candidate(store, f"{GOAL} [moa-engineered]", 0, 0),
    }
    return tmp, store, cids


class GoldDiggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.store, self.cids = _setup_store()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_vein_stats_parse_kinds_and_totals(self):
        veins = {v["kind"]: v for v in vein_stats(self.store, goal=GOAL)}
        self.assertEqual(set(veins), {"story", "offer", "event", "moa-engineered"})
        self.assertEqual(veins["story"]["impressions"], 120)
        self.assertEqual(veins["story"]["donation_cents"], 1500)
        self.assertEqual(veins["story"]["net_cents"], 1500)
        self.assertEqual(veins["event"]["donation_cents"], 0)

    def test_winner_gets_scale_verdict_and_leads(self):
        report = dig_report(self.store, goal=GOAL, seed=7, min_impressions=100)
        by_kind = {v["kind"]: v for v in report["veins"]}
        self.assertEqual(by_kind["story"]["verdict"], "scale")
        probs = {v["kind"]: v["selection_probability"] for v in report["veins"]}
        # Proven winner beats proven losers on sampling probability; the
        # untested arm may still lead on exploration, which is correct.
        self.assertGreater(probs["story"], probs["offer"])
        self.assertGreater(probs["story"], probs["event"])
        self.assertGreater(probs["moa-engineered"], 0)
        # ...but the proven leader is story by posterior mean
        means = {v["kind"]: v["posterior_mean_cents_per_impression"] for v in report["veins"]}
        self.assertEqual(max(means, key=means.get), "story")
        self.assertIn("story", report["next_action"])
        self.assertEqual(report["allocation"]["chosen_kind"], "story")
        self.assertEqual(report["totals"]["donation_cents"], 2000)

    def test_dry_vein_retired(self):
        report = dig_report(self.store, goal=GOAL, seed=7, min_impressions=100)
        by_kind = {v["kind"]: v for v in report["veins"]}
        self.assertEqual(by_kind["event"]["verdict"], "retire")
        self.assertIn("Retire", report["next_action"])

    def test_untested_vein_explores_with_support(self):
        report = dig_report(self.store, goal=GOAL, seed=7, min_impressions=100)
        by_kind = {v["kind"]: v for v in report["veins"]}
        fresh = by_kind["moa-engineered"]
        self.assertEqual(fresh["verdict"], "explore")
        self.assertGreater(fresh["selection_probability"], 0)

    def test_goal_filter(self):
        other = _publish_candidate(self.store, "other goal [story]", 50, 0)
        veins = vein_stats(self.store, goal=GOAL)
        self.assertNotIn(other, [v["candidate_id"] for v in veins])
        self.assertEqual(len(veins), 4)

    def test_deterministic_with_seed(self):
        first = dig_report(self.store, goal=GOAL, seed=42, min_impressions=100)
        second = dig_report(self.store, goal=GOAL, seed=42, min_impressions=100)
        self.assertEqual(first["allocation"]["chosen_candidate_id"],
                         second["allocation"]["chosen_candidate_id"])
        self.assertEqual(first["next_action"], second["next_action"])

    def test_report_event_recorded(self):
        dig_report(self.store, goal=GOAL, seed=7, min_impressions=100)
        self.assertEqual(self.store.events()[-1]["kind"], "gold_digger_report")

    def test_empty_report(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "empty.sqlite")
        try:
            report = dig_report(store, goal=GOAL, seed=1)
            self.assertEqual(report["veins"], [])
            self.assertIsNone(report["allocation"])
            self.assertIn("No published campaign candidates", report["next_action"])
            self.assertEqual(store.events()[-1]["kind"], "gold_digger_report")
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
