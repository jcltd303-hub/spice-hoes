"""Auditable mixture-of-agents planner grounded in recorded evidence."""
from .policy import recommend
AGENTS=("revenue","creative","distribution","risk")
def deliberate(persona,brief,stats,context,seed=None):
    own=next((s for s in stats if s["persona_id"]==persona["id"]),None)
    agents=[
      {"agent":"revenue","proposal":"Run the lowest-cost measurable test and attribute purchases, refunds, and distribution cost.","observed":own or {"persona_id":persona["id"],"published":0,"net_cents":0}},
      {"agent":"creative","proposal":f"Keep {persona['name']} identity-locked while testing {brief['theme']} through {brief['interest']}.","prompt":brief["prompt"]},
      {"agent":"distribution","proposal":f"Format for {brief['channel']} and preserve disclosure plus a traceable experiment ID."},
      {"agent":"risk","proposal":"Require fictional-adult identity, original likeness, disclosure, approval, and platform-compliant publishing."}]
    return {"architecture":"moa-v1","agents":agents,"retrieved_context":[{"source":c["source"],"score":c["score"],"text":c["text"][:500]} for c in context],
      "synthesis":{"brief":brief,"allocation_policy":recommend(stats,seed=seed),"decision_rule":"Net attributable revenue after refunds and recorded costs; retain exploration.","human_gate":"Asset release and publishing remain approval-gated."}}
