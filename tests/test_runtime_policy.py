import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.runtime_policy import DEFAULT_POLICY, RuntimePolicy


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "policy.sqlite")
        self.policy = RuntimePolicy(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_bootstrap_defaults_and_versioned_update(self):
        first = self.policy.current()
        self.assertEqual(first["version"], 1)
        self.assertEqual(first["values"]["daily_budget_cents"], DEFAULT_POLICY["daily_budget_cents"])

        second = self.policy.update(
            {"daily_budget_cents": 2500, "quality_threshold": 0.83},
            actor="operator",
            note="tighten spend and QA",
        )
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["values"]["daily_budget_cents"], 2500)
        self.assertEqual(second["values"]["quality_threshold"], 0.83)
        self.assertEqual(len(self.policy.history()), 2)
        self.assertTrue(self.policy.history()[0]["active"])
        self.assertFalse(self.policy.history()[1]["active"])

    def test_invalid_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            self.policy.update({"quality_threshold": 1.5}, actor="operator")
        with self.assertRaises(ValueError):
            self.policy.update({"unknown": 1}, actor="operator")
        with self.assertRaises(ValueError):
            self.policy.update({"max_pending_review": 0}, actor="operator")


if __name__ == "__main__":
    unittest.main()
