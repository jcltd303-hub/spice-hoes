import unittest
from spicecore.thompson_sampling import ThompsonSamplingBandit, recommend_thompson_sampling


class TestThompsonSampling(unittest.TestCase):
    def setUp(self):
        self.stats = [
            {"persona_id": "zara_voss", "name": "Zara Voss", "published": 10, "net_cents": 12000},  # $12/post
            {"persona_id": "tess_wilder", "name": "Tess Wilder", "published": 8, "net_cents": 4000},   # $5/post
            {"persona_id": "lila_hart", "name": "Lila Hart", "published": 12, "net_cents": 18000},   # $15/post (top)
            {"persona_id": "ruby_wren", "name": "Ruby Wren", "published": 6, "net_cents": -1000},   # -$1.6/post
            {"persona_id": "celeste_vale", "name": "Celeste Vale", "published": 2, "net_cents": 1500}, # $7.5/post (low n)
        ]

    def test_posterior_calculation_and_credible_intervals(self):
        bandit = ThompsonSamplingBandit()
        posteriors = bandit.compute_posteriors(self.stats)

        self.assertEqual(len(posteriors), 5)
        lila = next(p for p in posteriors if p["persona_id"] == "lila_hart")
        ruby = next(p for p in posteriors if p["persona_id"] == "ruby_wren")

        # Lila has high positive net mean
        self.assertGreater(lila["post_mean"], 1000)
        self.assertGreater(lila["ci_95"]["upper"], lila["ci_95"]["lower"])

        # Ruby has negative net mean
        self.assertLess(ruby["post_mean"], 0)

        # Untested/low sample persona Celeste has wider standard deviation
        celeste = next(p for p in posteriors if p["persona_id"] == "celeste_vale")
        self.assertGreater(celeste["post_std"], lila["post_std"])

    def test_sampling_probabilities_favor_top_performing_arm(self):
        bandit = ThompsonSamplingBandit()
        posteriors = bandit.compute_posteriors(self.stats)
        probs = bandit.sample_probabilities(posteriors, seed=42)

        # Lila should have the highest winning probability
        lila_idx = next(i for i, p in enumerate(posteriors) if p["persona_id"] == "lila_hart")
        ruby_idx = next(i for i, p in enumerate(posteriors) if p["persona_id"] == "ruby_wren")

        self.assertGreater(probs[lila_idx], 0.35)
        self.assertLess(probs[ruby_idx], 0.05)
        self.assertAlmostEqual(sum(probs), 1.0, places=4)

    def test_fatigue_decay_penalty_reduces_probability(self):
        bandit = ThompsonSamplingBandit(fatigue_decay_rate=0.25)

        # Without fatigue
        rec_fresh = bandit.recommend(self.stats, recent_history=[], seed=42)
        lila_fresh = next(a for a in rec_fresh["all_arms"] if a["persona_id"] == "lila_hart")

        # With 4 consecutive recent posts by Lila
        recent_history = ["lila_hart", "lila_hart", "lila_hart", "lila_hart"]
        rec_fatigued = bandit.recommend(self.stats, recent_history=recent_history, seed=42)
        lila_fatigued = next(a for a in rec_fatigued["all_arms"] if a["persona_id"] == "lila_hart")

        self.assertEqual(lila_fatigued["consecutive_recent_posts"], 4)
        self.assertLess(lila_fatigued["fatigue_penalty_factor"], 0.40)
        self.assertLess(lila_fatigued["selection_probability"], lila_fresh["selection_probability"])

    def test_convenience_function(self):
        res = recommend_thompson_sampling(self.stats, seed=123)
        self.assertEqual(res["policy_version"], "bayesian-thompson-sampling-v1")
        self.assertIn("ci_95", res)
        self.assertIn("uncertainty_note", res)
        self.assertEqual(len(res["all_arms"]), 5)


if __name__ == "__main__":
    unittest.main()
