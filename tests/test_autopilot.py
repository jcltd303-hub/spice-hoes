import tempfile
import unittest
from pathlib import Path

from spicecore.autopilot import CoreAutopilot
from spicecore.core import Store, load_personas


ROOT = Path(__file__).resolve().parents[1]


class FakeMoA:
    def deliberate(self, objective, persona):
        return {"synthesis": f"test {objective} for {persona['id']}"}


class FakePlanner:
    def __init__(self, store):
        self.store = store
        self.plan_calls = 0
        self.execute_calls = 0

    def plan(self, objective, persona, channel, offer, deliberation=None, variant_count=3):
        self.plan_calls += 1
        return {
            "plan_id": "plan-1",
            "persona_id": persona["id"],
            "channel": channel,
            "offer": offer,
            "variants": [
                {"id": f"v{i+1}", "theme": f"theme-{i+1}", "scene": ""}
                for i in range(variant_count)
            ],
        }

    def execute(self, plan, persona, generator, base_seed=None, cost_cents_per_asset=0):
        self.execute_calls += 1
        out = []
        for i, variant in enumerate(plan["variants"]):
            result = generator.generate(
                persona=persona,
                theme=variant["theme"],
                channel=plan["channel"],
                offer=plan["offer"],
                seed=None if base_seed is None else base_seed + i,
                cost_cents=cost_cents_per_asset,
            )
            out.append({
                "plan_id": plan["plan_id"],
                "variant_id": variant["id"],
                "candidate_id": result["candidate_id"],
                "asset": result,
            })
        return out


class FakeGenerator:
    def __init__(self, store):
        self.store = store

    def generate(self, persona, theme, channel, offer, scene="", seed=None, cost_cents=0):
        cid = self.store.propose(
            persona, theme, "still", channel, offer,
            asset_uri="data/fake.png",
            prompt="fake",
            model="fake",
            seed=str(seed) if seed is not None else None,
            cost_cents=cost_cents,
        )
        return {"candidate_id": cid, "status": "proposed"}


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "autopilot.sqlite")
        self.people = load_personas(ROOT / "personas")
        self.planner = FakePlanner(self.store)
        self.engine = CoreAutopilot(
            self.store,
            self.people,
            FakeMoA(),
            self.planner,
            FakeGenerator(self.store),
            min_experiences=4,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_run_creates_controlled_batch_with_bandit_fallback(self):
        result = self.engine.run_once(
            "Improve qualified affiliate traffic",
            "TikTok",
            "affiliate",
            variant_count=3,
            seed=7,
            cost_cents_per_asset=25,
            max_pending_review=6,
            daily_budget_cents=500,
        )
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["created_candidates"], 3)
        self.assertEqual(result["estimated_cost_cents"], 75)
        self.assertEqual(result["policy"]["source"], "contextual_bandit")
        self.assertEqual(self.engine.pending_review_count(), 3)

    def test_review_queue_limit_blocks_generation(self):
        first_person = self.people[0]
        for i in range(2):
            self.store.propose(
                first_person, f"old-{i}", "still", "TikTok", "affiliate"
            )
        result = self.engine.run_once(
            "test",
            "TikTok",
            "affiliate",
            variant_count=2,
            max_pending_review=3,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "review_queue_limit")
        self.assertEqual(self.planner.plan_calls, 0)

    def test_daily_budget_blocks_generation(self):
        result = self.engine.run_once(
            "test",
            "TikTok",
            "affiliate",
            variant_count=3,
            cost_cents_per_asset=100,
            daily_budget_cents=250,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "daily_budget_limit")
        self.assertEqual(self.planner.execute_calls, 0)


if __name__ == "__main__":
    unittest.main()
