import json
import tempfile
import unittest
from pathlib import Path

from spicecore.autopilot import CoreAutopilot
from spicecore.core import Store, load_personas
from spicecore.experiments import ExperimentPlanner
from spicecore.learning import LearningController, LearningNotReady
from spicecore.memory import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]


class FakeMoA:
    def deliberate(self, objective, persona):
        return {"synthesis": "test controlled framing"}


class FakePlanProvider:
    def chat(self, system, user, temperature=0.2):
        request = json.loads(user)
        n = request["variant_count"]
        return json.dumps({
            "hypothesis": "Framing changes qualified engagement.",
            "primary_metric": "clicks",
            "secondary_metrics": ["revenue"],
            "reversal_condition": "No arm improves after equal exposure.",
            "variants": [
                {
                    "id": f"v{i+1}",
                    "theme": f"theme-{i+1}",
                    "scene": f"scene-{i+1}",
                    "creative_angle": f"angle-{i+1}",
                    "caption_direction": "concise",
                    "cta": "learn more",
                }
                for i in range(n)
            ],
        })


class FakeGenerator:
    def __init__(self, store):
        self.store = store

    def generate(self, persona, theme, channel, offer, scene="", seed=None, cost_cents=0):
        cid = self.store.propose(
            persona,
            theme,
            "still",
            channel,
            offer,
            asset_uri=f"data/{theme}.png",
            prompt=scene,
            model="fake",
            seed=str(seed) if seed is not None else None,
            cost_cents=cost_cents,
        )
        return {"candidate_id": cid, "status": "proposed"}


class LearningClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "learning.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.planner = ExperimentPlanner(FakePlanProvider(), self.store)
        self.autopilot = CoreAutopilot(
            self.store,
            self.people,
            FakeMoA(),
            self.planner,
            FakeGenerator(self.store),
            min_experiences=4,
        )
        self.knowledge = KnowledgeBase(self.store)
        self.learning = LearningController(
            self.store,
            self.people,
            self.planner,
            self.knowledge,
            min_experiences=4,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def create_run(self):
        return self.autopilot.run_once(
            "Improve affiliate conversion",
            "TikTok",
            "affiliate",
            variant_count=2,
            seed=20,
            cost_cents_per_asset=25,
            max_pending_review=6,
            daily_budget_cents=500,
        )

    def test_settlement_waits_for_terminal_exposure_then_updates_rl_and_rag(self):
        run = self.create_run()
        with self.assertRaises(LearningNotReady):
            self.learning.settle_autopilot_run(
                run["run_id"],
                min_impressions_per_published_variant=1,
            )

        plan = self.planner.get(run["plan_id"])
        for index, variant in enumerate(plan["variants"]):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/{index}")
            self.store.record_outcome(
                cid, "impression", external_id=f"learning-imp-{index}"
            )
            if index == 1:
                self.store.record_outcome(
                    cid, "click", external_id="learning-click-1"
                )
                self.store.record_outcome(
                    cid, "purchase", 500, "learning-purchase-1"
                )

        result = self.learning.settle_autopilot_run(
            run["run_id"],
            min_impressions_per_published_variant=1,
        )
        again = self.learning.settle_autopilot_run(
            run["run_id"],
            min_impressions_per_published_variant=1,
        )

        self.assertEqual(result["status"], "settled")
        self.assertEqual(result["reward_cents"], 450)
        self.assertEqual(result["experience_id"], again["experience_id"])
        self.assertEqual(self.learning.policy.count(), 1)

        row = self.store.db.execute(
            "SELECT status FROM autopilot_run WHERE id=?",
            (run["run_id"],),
        ).fetchone()
        self.assertEqual(row["status"], "settled")

        hits = self.knowledge.search("observed experiment affiliate conversion")
        self.assertTrue(hits)
        self.assertTrue(any(h["source"].startswith("experiment:") for h in hits))

    def test_insufficient_exposure_does_not_create_learning(self):
        run = self.create_run()
        plan = self.planner.get(run["plan_id"])
        for index, variant in enumerate(plan["variants"]):
            cid = variant["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/{index}")

        with self.assertRaises(LearningNotReady):
            self.learning.settle_autopilot_run(
                run["run_id"],
                min_impressions_per_published_variant=1,
            )
        self.assertEqual(self.learning.policy.count(), 0)
        count = self.store.db.execute(
            "SELECT COUNT(*) FROM learning_closure"
        ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
