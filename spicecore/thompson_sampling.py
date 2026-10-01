"""Bayesian Thompson Sampling policy engine with fatigue decay penalties and credible intervals."""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple


class ThompsonSamplingBandit:
    """Bayesian Thompson Sampling bandit engine for persona and action allocation."""

    def __init__(
        self,
        prior_mean_cents: float = 0.0,
        prior_weight: float = 2.0,
        prior_std_cents: float = 500.0,
        fatigue_decay_rate: float = 0.20,
        monte_carlo_draws: int = 3000,
    ):
        self.prior_mean = prior_mean_cents
        self.prior_weight = prior_weight
        self.prior_std = prior_std_cents
        self.fatigue_decay_rate = fatigue_decay_rate
        self.monte_carlo_draws = monte_carlo_draws

    def compute_posteriors(
        self,
        stats: List[Dict[str, Any]],
        recent_history: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Calculates Bayesian conjugate Normal-Normal posterior parameters for each arm."""
        posteriors = []
        recent_history = recent_history or []

        # Count consecutive recent appearances from end of history
        consecutive_counts: Dict[str, int] = {}
        for s in stats:
            pid = s["persona_id"]
            k = 0
            for item in reversed(recent_history):
                if item == pid:
                    k += 1
                else:
                    break
            consecutive_counts[pid] = k

        for s in stats:
            pid = s["persona_id"]
            n = s.get("published", 0)
            net_cents = s.get("net_cents", 0.0)

            # Observed sample mean
            obs_mean = (net_cents / n) if n > 0 else 0.0

            # Estimate variance: use observed sample spread or conservative prior
            # For small n, blend between prior_std and sample standard deviation
            sample_std = max(100.0, self.prior_std / math.sqrt(max(1, n)))

            # Bayesian conjugate update for mean of normal distribution with known variance
            # post_precision = prior_precision + n * sample_precision
            prior_var = self.prior_std ** 2
            data_var = sample_std ** 2

            # Weighted posterior mean
            kappa_0 = self.prior_weight
            post_mean = (kappa_0 * self.prior_mean + n * obs_mean) / (kappa_0 + n)

            # Standard error of posterior mean
            post_var = (prior_var * data_var) / (data_var * kappa_0 + prior_var * n)
            post_std = math.sqrt(max(1.0, post_var))

            # 95% Bayesian Credible Interval
            ci_lower = round(post_mean - 1.96 * post_std, 2)
            ci_upper = round(post_mean + 1.96 * post_std, 2)

            # Fatigue penalty: exponential decay for consecutive posts without rotation
            k_consecutive = consecutive_counts.get(pid, 0)
            fatigue_factor = math.exp(-self.fatigue_decay_rate * k_consecutive)

            posteriors.append({
                "persona_id": pid,
                "name": s.get("name", pid),
                "published": n,
                "net_cents": net_cents,
                "obs_mean": round(obs_mean, 2),
                "post_mean": round(post_mean, 2),
                "post_std": round(post_std, 2),
                "ci_95": {"lower": ci_lower, "upper": ci_upper},
                "k_consecutive": k_consecutive,
                "fatigue_factor": round(fatigue_factor, 4),
            })

        return posteriors

    def sample_probabilities(
        self,
        posteriors: List[Dict[str, Any]],
        seed: Optional[int] = None,
    ) -> List[float]:
        """Runs Monte Carlo Thompson Sampling draws to compute exact winning probabilities."""
        rng = random.Random(seed)
        num_arms = len(posteriors)
        if num_arms == 0:
            return []

        wins = [0] * num_arms

        for _ in range(self.monte_carlo_draws):
            sampled_values = []
            for arm in posteriors:
                # Sample theta ~ Normal(post_mean, post_std)
                theta = rng.gauss(arm["post_mean"], arm["post_std"])
                # Apply fatigue penalty
                penalized_theta = theta * arm["fatigue_factor"]
                sampled_values.append(penalized_theta)

            # Best arm in this draw
            best_idx = max(range(num_arms), key=lambda i: sampled_values[i])
            wins[best_idx] += 1

        # Smooth slightly to ensure non-zero exploratory support for all arms
        probs = [(w + 1) / (self.monte_carlo_draws + num_arms) for w in wins]
        total = sum(probs)
        return [p / total for p in probs]

    def recommend(
        self,
        stats: List[Dict[str, Any]],
        recent_history: Optional[List[str]] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generates a complete Thompson Sampling recommendation with full Bayesian uncertainty notes."""
        if not stats:
            raise ValueError("Need at least one arm in stats")

        posteriors = self.compute_posteriors(stats, recent_history)
        probs = self.sample_probabilities(posteriors, seed=seed)

        # Select chosen arm according to sampling probabilities
        rng = random.Random(seed)
        chosen_idx = rng.choices(range(len(posteriors)), weights=probs)[0]
        chosen = posteriors[chosen_idx]

        all_arms_report = []
        for arm, prob in zip(posteriors, probs):
            all_arms_report.append({
                "persona_id": arm["persona_id"],
                "name": arm["name"],
                "published": arm["published"],
                "estimated_net_cents_per_published": arm["post_mean"],
                "selection_probability": round(prob, 4),
                "ci_95": arm["ci_95"],
                "consecutive_recent_posts": arm["k_consecutive"],
                "fatigue_penalty_factor": arm["fatigue_factor"],
            })

        return {
            "policy_version": "bayesian-thompson-sampling-v1",
            "method": "thompson_sampling_gaussian_conjugate",
            "persona_id": chosen["persona_id"],
            "name": chosen["name"],
            "selection_probability": round(probs[chosen_idx], 4),
            "estimated_net_cents_per_published": chosen["post_mean"],
            "supporting_published_count": chosen["published"],
            "ci_95": chosen["ci_95"],
            "consecutive_recent_posts": chosen["k_consecutive"],
            "fatigue_penalty_factor": chosen["fatigue_factor"],
            "uncertainty_note": (
                f"95% Bayesian credible interval [${chosen['ci_95']['lower']/100:.2f}, "
                f"${chosen['ci_95']['upper']/100:.2f}] via Normal-Normal conjugate update"
            ),
            "ranking_change_condition": (
                "Draws update dynamically with each new published post, impression, purchase, or refund"
            ),
            "all_arms": all_arms_report,
        }


def recommend_thompson_sampling(
    stats: List[Dict[str, Any]],
    recent_history: Optional[List[str]] = None,
    seed: Optional[int] = None,
    fatigue_decay_rate: float = 0.20,
) -> Dict[str, Any]:
    """Convenience functional interface for Thompson Sampling recommendation."""
    bandit = ThompsonSamplingBandit(fatigue_decay_rate=fatigue_decay_rate)
    return bandit.recommend(stats, recent_history=recent_history, seed=seed)
