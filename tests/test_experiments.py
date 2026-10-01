import json
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store, load_personas
from spicecore.experiments import ExperimentPlanner, ExperimentPlanError


ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    def chat(self, system, user, temperature=0.2):
        request = json.loads(user)
        n = request["variant_count"]
        return json.dumps({
            "hypothesis": "Changing framing changes qualified engagement.",
            "primary_metric": "link_clicks",
            "secondary_metrics": ["saves"],
            "reversal_condition": "No arm beats control after equal exposure.",
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
            persona, theme, "still", channel, offer,
            asset_uri=f"data/{theme}.png",
            prompt=scene,
            model="fake",
            seed=str(seed) if seed is not None else None,
            cost_cents=cost_cents,
        )
        return {"candidate_id": cid, "status": "proposed"}


class ExperimentPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "experiments.sqlite")
        self.people = load_personas(ROOT / "personas")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_plan_is_structured_audited_and_executable(self):
        planner = ExperimentPlanner(FakeProvider(), self.store)
        persona = self.people[0]
        plan = planner.plan(
            "Improve affiliate conversion",
            persona,
            "TikTok",
            "affiliate",
            deliberation={"synthesis": "test tighter framing"},
            variant_count=3,
        )
        self.assertEqual(len(plan["variants"]), 3)
        self.assertEqual(plan["primary_metric"], "link_clicks")

        results = planner.execute(
            plan,
            persona,
            FakeGenerator(self.store),
            base_seed=100,
            cost_cents_per_asset=25,
        )
        self.assertEqual(len(results), 3)
        self.assertEqual(
            [self.store.candidate(x["candidate_id"])["seed"] for x in results],
            ["100", "101", "102"],
        )
        loaded = planner.get(plan["plan_id"])
        self.assertTrue(all(v["candidate_id"] for v in loaded["variants"]))
        kinds = [e["kind"] for e in self.store.events()]
        self.assertIn("experiment_plan_created", kinds)
        self.assertEqual(kinds.count("experiment_variant_generated"), 3)

        for index, item in enumerate(results):
            cid = item["candidate_id"]
            self.store.review(cid, "approved", "operator")
            self.store.publish(cid, f"https://example.org/{index}")
            self.store.record_outcome(cid, "impression", external_id=f"imp-{index}")
            if index == 1:
                self.store.record_outcome(cid, "click", external_id="click-1")
                self.store.record_outcome(cid, "purchase", 500, "purchase-1")

        summary = planner.results(plan["plan_id"])
        self.assertEqual(summary["variants"][1]["net_cents"], 475)
        self.assertEqual(summary["variants"][1]["click_rate"], 1.0)
        self.assertEqual(summary["observed_leader_by_net_cents"], "v2")

    def test_invalid_variant_count_is_rejected(self):
        planner = ExperimentPlanner(FakeProvider(), self.store)
        with self.assertRaises(ExperimentPlanError):
            planner.plan("x", self.people[0], "TikTok", "affiliate", variant_count=1)


if __name__ == "__main__":
    unittest.main()
