"""Profit-first learning policy for autonomous influencer experiments.

Starts with contextual Thompson-style exploration. Deep-RL is deliberately gated until
there is enough attributed longitudinal experience; engagement is diagnostic, not reward.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, math, random
from typing import Iterable

REVENUE_KINDS={"sale","payout","sponsor_revenue","affiliate_revenue","subscription_revenue","digital_product_revenue"}
COST_KINDS={"fee","refund","chargeback","inference_cost","production_cost","storage_cost","distribution_cost","labor_cost"}
SHAPING={"hold_3s":1,"completion":2,"rewatch":2,"share":3,"profile_visit":2,"click":4,"add_to_cart":6,"checkout":8}

@dataclass(frozen=True)
class Arm:
    id: str
    persona_id: str
    geo: str
    language: str
    format: str
    offer_id: str
    revenue_model: str

class ProfitPolicy:
    """Select experiments by attributed contribution, uncertainty and bounded exploration."""
    def __init__(self, *, exploration_rate=.15, min_deeprl_experiences=5000, seed=0):
        if not 0 <= exploration_rate <= .5: raise ValueError("exploration_rate must be 0..0.5")
        if min_deeprl_experiences < 100: raise ValueError("Deep-RL gate is too small")
        self.exploration_rate=exploration_rate
        self.min_deeprl_experiences=min_deeprl_experiences
        self.rng=random.Random(seed)

    @staticmethod
    def reward(events: Iterable[dict], *, predicted_ltv_cents=0, ltv_discount=.25, risk_cost_cents=0):
        """Dollar-denominated reward. Engagement contributes only a tiny capped shaping term."""
        revenue=cost=shape=0
        for e in events:
            kind=e.get("kind"); amount=e.get("amount_cents",0)
            if type(amount) is not int or amount < 0: raise ValueError("nonnegative integer amount required")
            if kind in REVENUE_KINDS: revenue += amount
            elif kind in COST_KINDS: cost += amount
            elif kind in SHAPING: shape += SHAPING[kind]
        if predicted_ltv_cents < 0 or risk_cost_cents < 0: raise ValueError("cost/LTV cannot be negative")
        shaping_cents=min(25,shape) # never lets vanity metrics dominate economics
        return round(revenue-cost-risk_cost_cents+predicted_ltv_cents*ltv_discount+shaping_cents)

    def choose(self, arms: list[Arm], stats: dict[str,dict]) -> dict:
        if not arms: raise ValueError("at least one arm required")
        scored=[]
        for arm in arms:
            s=stats.get(arm.id,{})
            n=max(0,int(s.get("trials",0))); total=float(s.get("reward_cents",0))
            mean=total/n if n else 0.0
            uncertainty=1.0/math.sqrt(n+1)
            scored.append((mean,uncertainty,arm))
        explore=self.rng.random() < self.exploration_rate or all(stats.get(a.id,{}).get("trials",0)==0 for a in arms)
        if explore:
            # Prefer uncertainty while breaking ties reproducibly with RNG.
            top=max(x[1] for x in scored); pool=[x for x in scored if x[1]==top]
            chosen=self.rng.choice(pool)
        else:
            chosen=max(scored,key=lambda x:(x[0],x[1],x[2].id))
        return {"arm_id":chosen[2].id,"mode":"explore" if explore else "exploit",
                "estimated_reward_cents":round(chosen[0],2),"uncertainty":round(chosen[1],6)}

    def allocate(self, stats: dict[str,dict], total_budget_cents: int, *, floor_cents=0) -> dict[str,int]:
        """Rebalance capital without starving exploration arms."""
        if type(total_budget_cents) is not int or total_budget_cents < 0: raise ValueError("budget must be nonnegative")
        if not stats: return {}
        ids=sorted(stats); floor=min(floor_cents,total_budget_cents//len(ids))
        out={i:floor for i in ids}; remaining=total_budget_cents-floor*len(ids)
        weights={}
        for i in ids:
            s=stats[i]; n=max(1,int(s.get("trials",0)))
            mean=float(s.get("reward_cents",0))/n
            weights[i]=max(0.0,mean)+1/math.sqrt(n)
        denom=sum(weights.values()) or len(ids)
        assigned=0
        for i in ids[:-1]:
            add=int(remaining*weights[i]/denom); out[i]+=add; assigned+=add
        out[ids[-1]]+=remaining-assigned
        return out

    def deeprl_status(self, experiences: list[dict]) -> dict:
        """Fail closed: sequential policy training waits for attributed, mature rewards."""
        usable=[x for x in experiences if x.get("attributed") is True and x.get("mature") is True
                and isinstance(x.get("reward_cents"),(int,float))]
        return {"enabled":len(usable)>=self.min_deeprl_experiences,
                "usable_experiences":len(usable),"required":self.min_deeprl_experiences}

def arm_id(**dimensions):
    raw="|".join(f"{k}={dimensions[k]}" for k in sorted(dimensions))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]
