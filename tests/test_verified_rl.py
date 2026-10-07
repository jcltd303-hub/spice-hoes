import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.deeprl import DeepRLPolicy, InsufficientExperience


class VerifiedReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "replay.sqlite")
        self.legacy = DeepRLPolicy(self.store, ["a", "b"], min_experiences=1)
        self.episode = self.legacy.record([0.] * 6, "a", 99999, [0.] * 6, done=True)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_unverified_replay_and_snapshot_do_not_enter_production(self):
        self.legacy.b2 = [50., -50.]
        self.legacy.snapshot()
        production = DeepRLPolicy(self.store, ["a", "b"], min_experiences=1,
                                  verified_experiences_only=True)
        self.assertEqual(production.count(), 0)
        self.assertEqual(production.b2, [0., 0.])
        with self.assertRaises(InsufficientExperience):
            production.train()
        with self.assertRaises(InsufficientExperience):
            production.select([0.] * 6)

    def test_production_replay_and_snapshots_are_scoped_across_restarts(self):
        production = DeepRLPolicy(self.store, ["a", "b"], min_experiences=1,
                                  verified_experiences_only=True)
        observed = production.record([0.] * 6, "b", -100, [0.] * 6, done=True)
        self.store.db.execute("INSERT INTO rl_verified_experience VALUES(?)", (observed,))
        self.store.db.commit()
        trained = production.train(epochs=1)
        self.assertEqual(trained["experiences"], 1)
        self.assertLess(production.b2[1], 0.)
        self.assertEqual(production.b2[0], 0.)
        restarted = DeepRLPolicy(self.store, ["a", "b"], min_experiences=1,
                                 verified_experiences_only=True)
        self.assertEqual(restarted.b2, production.b2)
        self.assertEqual(restarted.count(), 1)
        self.assertEqual(self.legacy.count(), 2)
