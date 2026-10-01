import tempfile
import unittest
from pathlib import Path

from spicecore.control_plane import dispatch
from spicecore.core import Store, load_personas


ROOT = Path(__file__).resolve().parents[1]


class ControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "control.sqlite")
        self.personas = load_personas(ROOT / "personas")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_candidate_lifecycle_uses_canonical_store(self):
        persona = self.personas[0]
        created = dispatch(
            "propose",
            {
                "persona_id": persona["id"],
                "theme": "bridge-test",
                "format": "still",
                "channel": "test",
                "offer": "test-offer",
                "cost_cents": 11,
            },
            self.store,
            self.personas,
        )
        cid = created["id"]
        listed = dispatch("candidates", {}, self.store, self.personas)
        self.assertEqual(listed[0]["id"], cid)
        self.assertEqual(listed[0]["persona_name"], persona["name"])

        dispatch(
            "review",
            {"candidate_id": cid, "decision": "approved", "reviewer": "tester", "note": "ok"},
            self.store,
            self.personas,
        )
        dispatch(
            "publish",
            {"candidate_id": cid, "url": "https://example.test/post"},
            self.store,
            self.personas,
        )
        dispatch(
            "outcome",
            {"candidate_id": cid, "kind": "purchase", "amount_cents": 500},
            self.store,
            self.personas,
        )

        candidate = dispatch("candidates", {}, self.store, self.personas)[0]
        self.assertEqual(candidate["status"], "published")
        self.assertEqual(candidate["reviewer"], "tester")
        self.assertEqual(candidate["published_url"], "https://example.test/post")
        stats = dispatch("stats", {}, self.store, self.personas)
        row = next(item for item in stats if item["persona_id"] == persona["id"])
        self.assertEqual(row["revenue_cents"], 500)
        self.assertEqual(row["net_cents"], 489)

    def test_policy_decision_is_audited(self):
        baseline = len(self.store.events())
        result = dispatch("recommend", {"seed": 4}, self.store, self.personas)
        self.assertIn(result["persona_id"], {p["id"] for p in self.personas})
        self.assertEqual(len(self.store.events()), baseline)

        dispatch("recommend", {"seed": 4, "audit": True}, self.store, self.personas)
        self.assertEqual(self.store.events()[-1]["kind"], "policy_decision")

    def test_simulation_records_real_outcomes(self):
        persona = self.personas[0]
        cid = self.store.propose(persona, "sim", "still", "test", "offer")
        self.store.review(cid, "approved", "tester")
        self.store.publish(cid, "https://example.test/sim")
        out = dispatch(
            "simulate",
            {
                "candidate_id": cid,
                "impressions": 2,
                "clicks": 1,
                "purchases": 1,
                "purchaseCents": 700,
            },
            self.store,
            self.personas,
        )
        row = next(item for item in out["stats"] if item["persona_id"] == persona["id"])
        self.assertEqual(row["impressions"], 2)
        self.assertEqual(row["clicks"], 1)
        self.assertEqual(row["revenue_cents"], 700)

    def test_runtime_policy_update_and_rl_status(self):
        current = dispatch("policy", {}, self.store, self.personas)
        updated = dispatch(
            "policy_update",
            {
                "changes": {"daily_budget_cents": current["values"]["daily_budget_cents"] + 100},
                "actor": "tester",
                "note": "web-control-test",
            },
            self.store,
            self.personas,
        )
        self.assertEqual(
            updated["values"]["daily_budget_cents"],
            current["values"]["daily_budget_cents"] + 100,
        )
        self.assertGreater(updated["version"], current["version"])

        rl = dispatch("rl_status", {}, self.store, self.personas)
        self.assertEqual(rl["experiences"], 0)
        self.assertFalse(rl["ready"])
        self.assertEqual(rl["minimum_experiences"], updated["values"]["rl_min_experiences"])

    def test_knowledge_add_round_trip(self):
        item = dispatch(
            "knowledge_add",
            {
                "source": "operator",
                "title": "Control plane note",
                "body": "Approved knowledge from the operator desk.",
                "tags": ["ops", "control"],
            },
            self.store,
            self.personas,
        )
        self.assertEqual(item["title"], "Control plane note")
        hits = dispatch(
            "knowledge",
            {"query": "control plane note"},
            self.store,
            self.personas,
        )
        self.assertEqual(hits[0]["id"], item["id"])

    def test_doctor_reports_integrity_and_backlogs(self):
        result = dispatch("doctor", {}, self.store, self.personas)
        self.assertTrue(result["integrity"]["healthy"])
        self.assertEqual(result["counts"]["candidates_total"], 0)
        self.assertEqual(result["counts"]["pending_review"], 0)
        self.assertIn("rl", result)
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
