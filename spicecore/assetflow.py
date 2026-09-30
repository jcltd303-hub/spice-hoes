"""Autonomous local asset production with a review boundary."""
from __future__ import annotations
import json
from pathlib import Path
from .localdream import generate

def produce_job(store,personas,job_path,assets_dir="assets/generated",server_url=None,size=1024,steps=8,cfg=1.0,negative_prompt=""):
    path=Path(job_path); job=json.loads(path.read_text())
    if job.get("candidate_id"):
        return {"job":str(path),"candidate_id":job["candidate_id"],"asset":job.get("asset"),"status":job.get("status","awaiting_review"),"resumed":True}
    persona=next((p for p in personas if p["id"]==job["persona_id"]),None)
    if persona is None: raise ValueError("Job references unknown persona")
    brief=job["brief"]; seed=job.get("allocation",{}).get("seed")
    # policy output does not currently expose a generation seed; use caller/job seed only when present.
    output=Path(assets_dir)/persona["id"]/(path.stem+".png")
    job["status"]="generating"; path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
    try:
        meta=generate(brief["prompt"],output,negative_prompt,size,steps,cfg,seed,server_url)
        store.record_event("asset_generated",{"persona_id":persona["id"],"job":str(path),**meta})
        cid=store.propose(persona,brief["theme"],brief.get("format","still"),brief["channel"],"audience-test",meta["asset_uri"],brief["prompt"],"local-dream",str(meta["request"].get("seed","")),0)
        job.update({"status":"awaiting_review","asset":meta,"candidate_id":cid})
        path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
        return {"job":str(path),"candidate_id":cid,"asset":meta,"status":"awaiting_review","resumed":False}
    except Exception as exc:
        job["status"]="generation_failed"; job["last_error"]={"type":type(exc).__name__,"message":str(exc)}
        path.write_text(json.dumps(job,indent=2,ensure_ascii=False)+"\n")
        store.record_event("asset_generation_failed",{"persona_id":persona["id"],"job":str(path),"error_type":type(exc).__name__,"message":str(exc)})
        raise
