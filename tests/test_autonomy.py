import tempfile
import unittest
from pathlib import Path

from spicecore.autonomy import AutonomyEngine
from spicecore.core import Store, load_personas


ROOT = Path(__file__).resolve().parents[1]


class FakeMoA:
    def deliberate(self, objective, persona):
        return {"objective": objective, "persona_id": persona["id"], "proposal": "test"}


class FakeGenerator:
    def __init__(self, store):
        self.store = store

    def generate(self, persona, theme, channel, offer, scene="", seed=None, cost_cents=0):
        cid = self.store.propose(
            persona, theme, "still", channel, offer,
            asset_uri="data/assets/fake.png",
            prompt="fake",
            model="fake",
            seed=str(seed) if seed is not None else None,
            cost_cents=cost_cents,
        )
        return {
            "candidate_id": cid,
            "asset_id": "fake-asset",
            "asset_path": "data/assets/fake.png",
            "metadata_path": "data/assets/fake.png.json",
            "status": "proposed",
        }


class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "autonomy.sqlite")
        self.people = load_personas(ROOT / "personas")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_cycle_uses_bandit_before_rl_and_settles_net_reward_idempotently(self):
        engine = AutonomyEngine(
            self.store, self.people, FakeMoA(), FakeGenerator(self.store),
            min_experiences=4,
        )
        result = engine.run_cycle(
            objective="test monetization hypothesis",
            theme="city",
            channel="TikTok",
            offer="affiliate",
            seed=9,
            cost_cents=100,
        )
        self.assertEqual(result["policy"]["source"], "contextual_bandit")
        self.assertTrue(result["requires_human_review"])

        cid = result["asset"]["candidate_id"]
        self.store.review(cid, "approved", "operator")
        self.store.publish(cid, "https://example.org/post")
        self.store.record_outcome(cid, "purchase", 900, "purchase-auto-1")
        self.store.record_outcome(cid, "refund", 100, "refund-auto-1")
        self.store.record_outcome(cid, "distribution_cost", 50, "dist-auto-1")

        first = engine.settle_cycle(result["cycle_id"])
        second = engine.settle_cycle(result["cycle_id"])
        self.assertEqual(first["experience_id"], second["experience_id"])
        self.assertEqual(first["reward_cents"], 650)
        self.assertEqual(engine.policy.count(), 1)
        settled_events = [
            e for e in self.store.events()
            if e["kind"] == "autonomy_cycle_settled"
        ]
        self.assertEqual(len(settled_events), 1)


if __name__ == "__main__":
    unittest.main()
