"""One-shot next-batch planning: evidence -> allocation -> MoA -> production job."""
from __future__ import annotations
import json
from pathlib import Path
from .moa import deliberate
from .policy import recommend
from .production import free_production_plan
from .rag import LocalRAG
from .workflow import build_briefs

def plan_next_batch(store,personas,theme,channel,output_dir="jobs",seed=None,use_avatar=False,knowledge_paths=None):
    stats=store.stats(personas)
    allocation=recommend(stats,seed=seed)
    persona=next(p for p in personas if p["id"]==allocation["persona_id"])
    brief=next(b for b in build_briefs(personas,theme,channel,seed) if b["persona_id"]==persona["id"])
    paths=knowledge_paths or ["project.md","identity","personas"]
    context=LocalRAG.from_paths(paths).search(f"{persona['name']} {theme} {channel} monetization identity",5)
    decision=deliberate(persona,brief,stats,context,seed)
    production=free_production_plan(brief,use_avatar)
    payload={"schema_version":1,"persona_id":persona["id"],"allocation":allocation,"decision":decision,"brief":brief,"production":production,"generation_seed":seed,"status":"awaiting_generation"}
    out=Path(output_dir)/f"next-{persona['id']}-{theme}.json"; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
    event=store.record_event("batch_planned",{"persona_id":persona["id"],"theme":theme,"channel":channel,"job":str(out),"policy_version":allocation["policy_version"]})
    return {"job":str(out),"event_id":event["id"],**payload}
