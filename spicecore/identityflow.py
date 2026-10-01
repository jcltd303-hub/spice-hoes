"""Controlled identity-lock batches for a fictional adult persona."""
from __future__ import annotations
import json
from pathlib import Path
from .assetflow import produce_job

CELESTE_LOCK_PROMPT = """Photorealistic editorial portrait of Celeste Vale, one original fictional adult woman age 32. Warm olive skin with visible natural texture and faint freckles; dark brown almond eyes; slightly asymmetric arched brows; straight softly rounded nose; natural full lips; a small beauty mark on her left cheek (viewer right); espresso-brown collarbone-length softly wavy hair. Understated sculptural gold earrings, restrained makeup. Front-facing head-and-shoulders portrait, neutral candid expression, soft window daylight, eye-level 85mm photographic perspective, shallow depth of field. Preserve realistic anatomy and skin detail. One woman only; no text, watermark, celebrity likeness, illustration, or exaggerated retouching."""

NEGATIVE = "cartoon, anime, illustration, CGI, doll, child, teenager, deformed, distorted face, duplicate person, extra limbs, blurry, low quality, plastic skin, text, watermark"

def create_identity_job(persona, output_dir="jobs/identity", seed=42, candidate_count=6):
 if persona["id"]!="celeste_vale": raise ValueError("Identity v1 prompt currently exists only for celeste_vale")
 payload={"schema_version":1,"job_type":"identity_lock","persona_id":persona["id"],"generation_seed":seed,
          "candidate_count":candidate_count,"profile":"cyberrealistic-v10","status":"awaiting_generation",
          "brief":{"persona_id":persona["id"],"theme":"identity-lock-v1","format":"reference-portrait",
                   "channel":"internal-review","prompt":CELESTE_LOCK_PROMPT}}
 out=Path(output_dir)/f"{persona['id']}-identity-v1.json"; out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
 return out

def run_identity_batch(store, personas, persona_id="celeste_vale", output_dir="jobs/identity",
                       assets_dir="assets/generated", server_url=None, seed=42, candidate_count=6):
 persona=next((p for p in personas if p["id"]==persona_id),None)
 if persona is None: raise ValueError("Unknown persona")
 path=create_identity_job(persona,output_dir,seed,candidate_count)
 return produce_job(store,personas,path,assets_dir,server_url,None,None,None,NEGATIVE,candidate_count,"cyberrealistic-v10")
