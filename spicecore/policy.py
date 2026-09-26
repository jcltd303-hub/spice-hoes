"""Transparent allocation policy; predictions are estimates, not explanations."""

import random
from math import sqrt


def recommend(stats: list[dict], seed: int | None = None, exploration: float = 0.30) -> dict:
    if not stats or not 0 <= exploration <= 1:
        raise ValueError('Need arms and an exploration fraction between zero and one')
    rng = random.Random(seed)
    # A one-observation zero-reward prior prevents a single sale from determining the portfolio.
    values = [(s['net_cents'] / (s['published'] + 1)) for s in stats]
    untested = [i for i, s in enumerate(stats) if s['published'] == 0]
    # If some personas have no published tests, give them first opportunity.
    if untested:
        probabilities = [1 / len(untested) if i in untested else 0.0 for i in range(len(stats))]
        method = 'untested_rotation'
    else:
        leader = max(range(len(stats)), key=lambda i: (values[i], -i))
        probabilities = [exploration / len(stats)] * len(stats)
        probabilities[leader] += 1 - exploration
        method = 'epsilon_greedy'
    index = rng.choices(range(len(stats)), weights=probabilities)[0]
    chosen = stats[index]
    return {
        'policy_version': 'epsilon-greedy-v1', 'method': method,
        'persona_id': chosen['persona_id'], 'name': chosen['name'],
        'selection_probability': probabilities[index],
        'estimated_net_cents_per_published': round(values[index], 2),
        'supporting_published_count': chosen['published'],
        'uncertainty_note': 'Exploratory heuristic; no calibrated confidence interval',
        'ranking_change_condition': 'Changes when additional recorded net outcomes change the smoothed ranking',
        'all_arms': [{'persona_id': s['persona_id'], 'published': s['published'],
                      'estimated_net_cents_per_published': round(v, 2),
                      'selection_probability': round(prob, 6)}
                     for s, v, prob in zip(stats, values, probabilities)]
    }
