"""MoA-engineered donation campaigns.

Combines the deterministic Nextdoor campaign generator with the
Mixture-of-Agents deliberation: the four experts (revenue, creative, growth,
risk) assess the generated variants, and the aggregator returns an engineered
plan — variant ranking, concrete copy refinements, risk flags, one engineered
post, and a measurement design.

MoA output is advisory, never authoritative:

- Every piece of MoA-suggested copy is re-validated against the copy policy.
  Only clean copy is proposed; dirty copy is reported, not published.
- Everything stays ``proposed`` until a human approves it in the review desk.
- Nothing auto-posts to Nextdoor (manual handoff only).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .distribution.nextdoor import generate_campaign, validate_copy
from .moa import MixtureOfAgents

CAMPAIGN_MOA_CONSTRAINTS = """HARD CONSTRAINTS (non-negotiable):
- Do not promise or guarantee donations, earnings, or any outcome. Every claim about performance is a hypothesis to be measured, never a fact.
- The voice is {persona_name}, a disclosed fictional AI persona. Copy must NEVER claim to be a real human, a real neighbor, or imply otherwise.
- No pressure or manipulation tactics (no "act now", guilt-tripping, or false urgency).
- Never request payment-card or banking details. Donations go only through the official offer link.
- Nextdoor has no posting API: assume a human reviews every candidate, then posts manually from a verified neighborhood account.
- Any recommended_copy MUST end with this exact disclosure, verbatim: "{disclosure}"."""

CAMPAIGN_MOA_SCHEMA_NOTE = """The aggregator should additionally include these keys in its synthesis object:
- "variant_ranking": ordered list of variant_ids, best first, each with a one-line reason.
- "recommended_copy": ONE full engineered Nextdoor post (title line, blank line, then body), ending with the disclosure above.
- "refinements": concrete copy edits for the ranked variants."""


def build_campaign_objective(
    persona: Dict[str, Any],
    goal: str,
    cause: str,
    neighborhood: str,
    offer: str,
    variants: List[Dict[str, Any]],
) -> str:
    """Build the MoA objective text for a donation campaign."""
    disclosure = str(persona.get("disclosure", "")).strip()
    lines = [
        "Engineer a donation campaign for Nextdoor.",
        "",
        f"GOAL: {goal}",
        f"CAUSE: {cause}",
        f"NEIGHBORHOOD: {neighborhood}",
        f"OFFER/LINK: {offer}",
        "",
        "CANDIDATE VARIANTS (seed-generated, already policy-checked):",
    ]
    for v in variants:
        lines.append(f"[{v['variant_id']}] (kind: {v['kind']})")
        lines.append(f"Title: {v['title']}")
        lines.append(v["body"])
        lines.append("")
    lines.append(
        CAMPAIGN_MOA_CONSTRAINTS.format(
            persona_name=persona.get("name", persona.get("id", "persona")),
            disclosure=disclosure,
        )
    )
    lines.append("")
    lines.append(CAMPAIGN_MOA_SCHEMA_NOTE)
    return "\n".join(lines)


def engineer_campaign(
    store,
    provider,
    persona: Dict[str, Any],
    goal: str,
    cause: str,
    neighborhood: str,
    offer: str = "none",
    seed: Optional[int] = None,
    count: int = 3,
    embedder=None,
) -> Dict[str, Any]:
    """Generate variants, deliberate with MoA, and propose policy-clean candidates.

    Returns the engineered plan: ranked variants, refinements, the validated
    MoA post (if any), measurement design, and the full deliberation record.
    """
    if not persona.get("id") or not persona.get("disclosure"):
        raise ValueError("persona with id and disclosure is required")

    variants = generate_campaign(
        persona=persona,
        goal=goal,
        cause=cause,
        neighborhood=neighborhood,
        offer=offer,
        seed=seed,
        count=count,
    )
    for v in variants:
        if v.violations:
            raise ValueError(f"generated copy failed policy check: {v.violations}")

    objective = build_campaign_objective(
        persona, goal, cause, neighborhood, offer, [v.to_dict() for v in variants]
    )
    moa = MixtureOfAgents(provider, store, embedder=embedder)
    deliberation = moa.deliberate(objective, persona)  # records moa_deliberation
    synthesis = deliberation.get("synthesis", {}) or {}

    recommended = synthesis.get("recommended_copy", "")
    recommended = recommended.strip() if isinstance(recommended, str) else ""
    disclosure = str(persona["disclosure"]).strip()
    if recommended:
        recommended_violations = validate_copy(recommended, require_disclosure=disclosure)
    else:
        recommended_violations = ["no recommended copy supplied by MoA"]

    seed_str = str(seed) if seed is not None else None
    proposed: List[Dict[str, Any]] = []
    for v in variants:
        cid = store.propose(
            persona,
            theme=f"{goal} [{v.kind}]",
            format="post",
            channel="nextdoor",
            offer=offer,
            prompt=v.body,
            model="campaign-generator",
            seed=seed_str,
            cost_cents=0,
        )
        proposed.append({"candidate_id": cid, **v.to_dict()})

    recommended_proposed = False
    recommended_candidate_id: Optional[str] = None
    if recommended and not recommended_violations:
        recommended_candidate_id = store.propose(
            persona,
            theme=f"{goal} [moa-engineered]",
            format="post",
            channel="nextdoor",
            offer=offer,
            prompt=recommended,
            model="campaign-moa",
            seed=seed_str,
            cost_cents=0,
        )
        recommended_proposed = True

    ranking = synthesis.get("variant_ranking", [])
    if not isinstance(ranking, list):
        ranking = []
    refinements = synthesis.get("refinements", [])
    if not isinstance(refinements, list):
        refinements = [refinements]

    plan = {
        "goal": goal,
        "cause": cause,
        "neighborhood": neighborhood,
        "offer": offer,
        "seed": seed,
        "variants": proposed,
        "variant_ranking": ranking,
        "refinements": refinements,
        "recommended_copy": recommended,
        "recommended_violations": recommended_violations,
        "recommended_proposed": recommended_proposed,
        "recommended_candidate_id": recommended_candidate_id,
        "measurement": {
            "test_design": synthesis.get("test_design"),
            "success_metrics": synthesis.get("success_metrics"),
            "reversal_condition": synthesis.get("reversal_condition"),
        },
        "constraints": synthesis.get("constraints"),
        "deliberation_id": deliberation.get("objective"),
    }
    store.record_event("campaign_engineered", {
        "goal": goal,
        "cause": cause,
        "neighborhood": neighborhood,
        "offer": offer,
        "seed": seed,
        "candidate_ids": [p["candidate_id"] for p in proposed]
        + ([recommended_candidate_id] if recommended_candidate_id else []),
        "variant_ranking": ranking,
        "recommended_proposed": recommended_proposed,
        "recommended_violations": recommended_violations,
    })
    return plan
