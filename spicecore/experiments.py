"""Bounded exploration over comparable, closed-window experiment arms."""
import random

class ExperimentPolicy:
 def recommend(self,arms,seed=0,exploration=.2):
  eligible=[a for a in arms if a.get('window_closed') is True and type(a.get('contribution_cents')) is int and type(a.get('trials')) is int and a['trials']>0]
  if not eligible: return {'status':'insufficient_evidence','selected_arm':None}
  currencies={a.get('currency') for a in eligible}
  if len(currencies)!=1: raise ValueError('Compare one currency at a time')
  rng=random.Random(seed); values=[a['contribution_cents']/(a['trials']+1) for a in eligible]; leader=max(range(len(eligible)),key=lambda i:values[i])
  if rng.random()<exploration: idx=rng.randrange(len(eligible))
  else: idx=leader
  return {'status':'selected','selected_arm':eligible[idx]['id'],'currency':eligible[idx]['currency'],'method':'bounded_epsilon_greedy','sample_size':eligible[idx]['trials'],'uncertainty':'heuristic; closed outcome window, not causal certainty'}
