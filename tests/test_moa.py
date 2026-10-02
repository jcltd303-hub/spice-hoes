import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.moa import MixtureOfAgents


class FakeProvider:
    model_name = "fake:test"

    def __init__(self):
        self.calls = []

    def chat(self, system, user, temperature=0.4):
        self.calls.append((system, user, temperature))
        if len(self.calls) <= 4:
            return '{"assessment":"ok","hypotheses":[],"action":"test","metric":"revenue","risk":"low"}'
        return '{"proposed_action":"test","monetization_mechanism":"affiliate","evidence":[],"test_design":"A/B","success_metrics":["revenue"],"constraints":[],"reversal_condition":"negative result"}'


class MoATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "moa.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_multiple_experts_then_aggregator_and_event(self):
        provider = FakeProvider()
        moa = MixtureOfAgents(provider, self.store)
        moa.knowledge.add("guide", "Revenue", "Track attributable net revenue and retention.", ["metrics"])
        result = moa.deliberate("Choose the next measurable content experiment for net revenue and retention", {"id": "zara", "age": 29})
        self.assertEqual(result["architecture"], "moa-v3-heterogeneous-openrouter")
        self.assertEqual(len(result["experts"]), 4)
        self.assertEqual(len(provider.calls), 5)
        self.assertEqual(result["successful_experts"], 4)
        self.assertIn("synthesis", result)
        self.assertIn("aggregator", result)
        self.assertTrue(all(item["structured"] for item in result["experts"]))
        self.assertTrue(all("actual_model" in item for item in result["experts"]))
        self.assertTrue(result["retrieval"])
        self.assertEqual(self.store.events()[-1]["kind"], "moa_deliberation")


if __name__ == "__main__":
    unittest.main()
