"""GoldDigger: donation-campaign administration and optimization.

Reads published campaign candidates and their recorded outcomes from the
ledger, scores each variant (a "vein") on observed donation performance, and
uses Thompson sampling to recommend where the next unit of effort goes: scale
the winner, keep exploring, or retire dry veins.

Honest optimization only. It reallocates effort toward what measurably works.
It never fabricates outcomes, never pressures donors, never makes earnings
claims, and never auto-posts — Nextdoor stays manual-handoff.

Donation model: a `purchase` outcome recorded against a published candidate is
a donation of `amount_cents`. Impressions are the exposure trials.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .thompson_sampling import ThompsonSamplingBandit

CHANNEL = "nextdoor"
_KIND_RE = re.compile(r"\[(story|offer|event|moa-engineered)\]\s*$")


def _parse_kind(theme: str) -> str:
    match = _KIND_RE.search(theme or "")
    return match.group(1) if match else "unknown"


def vein_stats(
    store,
    goal: Optional[str] = None,
    channel: str = CHANNEL,
) -> List[Dict[str, Any]]:
    """Per-candidate donation performance for published campaign candidates."""
    rows = store.db.execute(
        "SELECT * FROM candidates WHERE channel=? AND status='published' ORDER BY created_at",
        (channel,),
    ).fetchall()
    outcome_rows = store.db.execute(
        "SELECT kind, payload FROM events WHERE kind IN ('impression','click','purchase','refund')"
    ).fetchall()

    veins = []
    for row in rows:
        cid = row["id"]
        if goal and not str(row["theme"]).startswith(goal):
            continue
        impressions = clicks = 0
        donation_cents = refund_cents = 0
        for ev in outcome_rows:
            item = json.loads(ev["payload"])
            if item.get("candidate_id") != cid:
                continue
            kind = ev["kind"]
            if kind == "impression":
                impressions += int(item.get("count", 1))
            elif kind == "click":
                clicks += int(item.get("count", 1))
            elif kind == "purchase":
                donation_cents += int(item.get("amount_cents", 0))
            elif kind == "refund":
                refund_cents += int(item.get("amount_cents", 0))
        cost_cents = row["cost_cents"] or 0
        net_cents = donation_cents - refund_cents - cost_cents
        veins.append({
            "candidate_id": cid,
            "kind": _parse_kind(row["theme"]),
            "theme": row["theme"],
            "persona_id": row["persona_id"],
            "offer": row["offer"],
            "impressions": impressions,
            "clicks": clicks,
            "donation_cents": donation_cents,
            "refund_cents": refund_cents,
            "cost_cents": cost_cents,
            "net_cents": net_cents,
            "donation_cents_per_1k_impressions": (
                round(donation_cents / impressions * 1000, 2) if impressions else 0.0
            ),
        })
    return veins


def _verdict(vein: Dict[str, Any], is_leader: bool, min_impressions: int) -> str:
    """Transparent scale / explore / retire rule. Explainable, no black box."""
    impressions = vein["impressions"]
    if impressions < min_impressions:
        return "explore"  # not enough evidence yet
    if vein["net_cents"] <= 0 and impressions >= 2 * min_impressions:
        return "retire"  # dry vein at real exposure
    if is_leader and vein["net_cents"] > 0:
        return "scale"
    return "explore"


def dig_report(
    store,
    goal: Optional[str] = None,
    channel: str = CHANNEL,
    seed: Optional[int] = None,
    min_impressions: int = 100,
    bandit: Optional[ThompsonSamplingBandit] = None,
) -> Dict[str, Any]:
    """Administer the campaign: score veins, allocate next effort, report."""
    veins = vein_stats(store, goal=goal, channel=channel)
    bandit = bandit or ThompsonSamplingBandit()

    if not veins:
        report = {
            "goal": goal,
            "channel": channel,
            "veins": [],
            "allocation": None,
            "next_action": (
                "No published campaign candidates yet. Generate one with `campaign` or "
                "`campaign-moa`, approve it in the review desk, post it manually, then "
                "record impressions and donations with the `outcome` command."
            ),
        }
        store.record_event("gold_digger_report", {
            "goal": goal, "channel": channel, "veins": 0,
            "next_action": report["next_action"],
        })
        return report

    arms = [
        {
            "persona_id": v["candidate_id"],  # bandit arm key
            "name": f"{v['kind']} ({v['candidate_id'][:8]})",
            "published": v["impressions"],  # exposure trials
            "net_cents": float(v["net_cents"]),
        }
        for v in veins
    ]
    allocation = bandit.recommend(arms, seed=seed)

    for v in veins:
        arm = next(a for a in allocation["all_arms"] if a["persona_id"] == v["candidate_id"])
        v["selection_probability"] = arm["selection_probability"]
        v["posterior_mean_cents_per_impression"] = arm["estimated_net_cents_per_published"]
        v["ci_95_cents"] = arm["ci_95"]

    # Leader = best proven vein by posterior mean (evidence-backed), not the
    # sampling draw — the draw still drives exploration via next_action.
    proven = [v for v in veins if v["impressions"] >= min_impressions]
    leader_id = (
        max(proven, key=lambda v: v["posterior_mean_cents_per_impression"])["candidate_id"]
        if proven else None
    )
    for v in veins:
        v["verdict"] = _verdict(v, is_leader=(v["candidate_id"] == leader_id),
                               min_impressions=min_impressions)

    chosen = next(v for v in veins if v["candidate_id"] == allocation["persona_id"])
    scalers = [v for v in veins if v["verdict"] == "scale"]
    retired = [v for v in veins if v["verdict"] == "retire"]

    if scalers:
        top = scalers[0]
        next_action = (
            f"Next manual post: the {top['kind']} variant (candidate {top['candidate_id'][:8]}) — "
            f"leads on observed donations (${top['donation_cents']/100:.2f} from "
            f"{top['impressions']} impressions, selection probability "
            f"{top['selection_probability']}). Keep the explore veins in rotation."
        )
    else:
        next_action = (
            f"Next manual post: the {chosen['kind']} variant (candidate "
            f"{chosen['candidate_id'][:8]}) — bandit's current pick (selection probability "
            f"{chosen['selection_probability']}). Evidence is still thin; keep exploring."
        )
    if retired:
        next_action += (
            f" Retire {len(retired)} dry vein(s): "
            + ", ".join(f"{v['kind']} ({v['candidate_id'][:8]})" for v in retired)
            + " — zero net donations at real exposure."
        )

    report = {
        "goal": goal,
        "channel": channel,
        "policy": "bayesian-thompson-sampling-v1",
        "min_impressions": min_impressions,
        "totals": {
            "veins": len(veins),
            "impressions": sum(v["impressions"] for v in veins),
            "donation_cents": sum(v["donation_cents"] for v in veins),
            "net_cents": sum(v["net_cents"] for v in veins),
        },
        "veins": veins,
        "allocation": {
            "chosen_candidate_id": allocation["persona_id"],
            "chosen_kind": chosen["kind"],
            "selection_probability": allocation["selection_probability"],
            "uncertainty_note": allocation["uncertainty_note"],
        },
        "next_action": next_action,
    }
    store.record_event("gold_digger_report", {
        "goal": goal,
        "channel": channel,
        "veins": [
            {
                "candidate_id": v["candidate_id"],
                "kind": v["kind"],
                "impressions": v["impressions"],
                "donation_cents": v["donation_cents"],
                "net_cents": v["net_cents"],
                "selection_probability": v["selection_probability"],
                "verdict": v["verdict"],
            }
            for v in veins
        ],
        "next_action": next_action,
    })
    return report
