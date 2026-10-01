"""Persist a human-selected canonical identity anchor."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

def select_identity(store, persona_id, candidate_id, reference_dir="identity/references"):
 candidate=store.candidate(candidate_id)
 if candidate["persona_id"]!=persona_id: raise ValueError("Candidate belongs to another persona")
 if candidate["status"]!="proposed": raise ValueError("Identity anchor must be an unreviewed candidate")
 src=Path(candidate["asset_uri"])
 if not src.is_file(): raise ValueError("Candidate asset is missing")
 digest=hashlib.sha256(src.read_bytes()).hexdigest()
 outdir=Path(reference_dir); outdir.mkdir(parents=True,exist_ok=True)
 ext=src.suffix.lower() or ".png"; dest=outdir/f"{persona_id}-{digest[:12]}{ext}"
 if not dest.exists(): dest.write_bytes(src.read_bytes())
 manifest=outdir/f"{persona_id}.json"
 payload={"schema_version":1,"persona_id":persona_id,"candidate_id":candidate_id,
          "reference_asset":str(dest),"sha256":digest,"source_asset":str(src),
          "model":candidate.get("model"),"seed":candidate.get("seed"),"prompt":candidate.get("prompt")}
 manifest.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
 store.review(candidate_id,"approved","identity-selection","canonical identity anchor")
 store.record_event("identity_reference_selected",payload)
 return {"manifest":str(manifest),**payload}
