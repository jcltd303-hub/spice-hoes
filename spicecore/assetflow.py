"""Autonomous Local Dream exploration with a human selection boundary."""
from __future__ import annotations
import json
from pathlib import Path
from .localdream import generate

def produce_job(store,personas,job_path,assets_dir="assets/generated",server_url=None,size=None,steps=None,cfg=None,
                negative_prompt="",candidate_count=6,profile="cyberrealistic-v10"):
 path=Path(job_path); job=json.loads(path.read_text())
 persona=next((p for p in personas if p["id"]==job["persona_id"]),None)
 if persona is None: raise ValueError("Job references unknown persona")
 brief=job["brief"]; base_seed=job.get("generation_seed")
 output_dir=Path(assets_dir)/persona["id"]/path.stem
 if job.get("candidate_count") is not None and ids:\n  candidate_count=int(job["candidate_count"])\n job["status"]="exploring"; job["profile"]=profile; job["candidate_count"]=candidate_count
 path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
 assets=list(job.get("assets",[])); ids=list(job.get("candidate_ids",[])); resumed_from=len(ids)
 if len(ids)>=candidate_count and job.get("status")=="awaiting_review":
  return {"job":str(path),"candidate_ids":ids,"assets":assets,"status":"awaiting_review","resumed":True}
 try:
  for index in range(len(ids),candidate_count):
   seed=(base_seed+index) if base_seed is not None else None
   output=output_dir/f"{index+1:02d}.png"
   meta=generate(brief["prompt"],output,negative_prompt,size,steps,cfg,seed,server_url,profile=profile)
   meta["exploration_index"]=index+1; assets.append(meta)
   store.record_event("asset_generated",{"persona_id":persona["id"],"job":str(path),**meta})
   cid=store.propose(persona,brief["theme"],brief.get("format","still"),brief["channel"],"audience-test",
                     meta["asset_uri"],brief["prompt"],f"local-dream:{profile}",str(meta["request"].get("seed","")),0)
   ids.append(cid)
   # Persist after every successful image so an interrupted phone run retains provenance.
   job.update({"assets":assets,"candidate_ids":ids})
   path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
  job["status"]="awaiting_review"
  path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
  return {"job":str(path),"candidate_ids":ids,"assets":assets,"status":"awaiting_review","resumed":resumed_from>0}
 except Exception as exc:
  job["status"]="generation_failed"; job["last_error"]={"type":type(exc).__name__,"message":str(exc)}
  path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
  store.record_event("asset_generation_failed",{"persona_id":persona["id"],"job":str(path),"error_type":type(exc).__name__,"message":str(exc)})
  raise
