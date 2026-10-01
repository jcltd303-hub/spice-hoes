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
        return f"answer-{len(self.calls)}"


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
        result = moa.deliberate("Choose the next measurable content experiment", {"id": "zara", "age": 29})
        self.assertEqual(result["architecture"], "moa-v1")
        self.assertEqual(len(result["experts"]), 4)
        self.assertEqual(len(provider.calls), 5)
        self.assertTrue(result["retrieval"])
        self.assertEqual(self.store.events()[-1]["kind"], "moa_deliberation")


if __name__ == "__main__":
    unittest.main()
