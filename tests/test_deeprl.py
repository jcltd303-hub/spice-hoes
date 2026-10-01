import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.deeprl import DeepRLPolicy, InsufficientExperience


class DeepRLTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "rl.sqlite")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_policy_is_gated_then_trains_and_selects(self):
        policy = DeepRLPolicy(self.store, ["a", "b"], hidden=4, seed=1, min_experiences=4)
        with self.assertRaises(InsufficientExperience):
            policy.select([0.0] * 6)
        for i in range(4):
            state = [i / 10.0] * 6
            nxt = [(i + 1) / 10.0] * 6
            policy.record(state, "a" if i % 2 == 0 else "b", 100 + i * 10, nxt)
        trained = policy.train(epochs=3, learning_rate=0.005)
        self.assertEqual(trained["experiences"], 4)
        decision = policy.select([0.2] * 6, epsilon=0.0, seed=2)
        self.assertIn(decision["action_id"], {"a", "b"})
        self.assertEqual(self.store.events()[-1]["kind"], "rl_policy_decision")

        reloaded = DeepRLPolicy(
            self.store, ["a", "b"], hidden=4, seed=999, min_experiences=4
        )
        self.assertEqual(reloaded.w1, policy.w1)
        self.assertEqual(reloaded.b2, policy.b2)


    def test_record_external_id_is_idempotent(self):
        policy = DeepRLPolicy(self.store, ["a", "b"], hidden=4, seed=1, min_experiences=1)
        first = policy.record([0.0] * 6, "a", 100, [0.1] * 6, external_id="cycle-1")
        second = policy.record([0.0] * 6, "a", 100, [0.1] * 6, external_id="cycle-1")
        self.assertEqual(first, second)
        self.assertEqual(policy.count(), 1)


if __name__ == "__main__":
    unittest.main()
