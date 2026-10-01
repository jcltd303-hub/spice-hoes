"""Generate controlled scene variations from a canonical identity reference."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from .localdream import generate

SCENES={
 "hotel-lobby":"standing in an elegant boutique hotel lobby, tailored burgundy jacket, reviewing fabric samples, warm practical lamps and soft window light",
 "record-shop":"browsing jazz records at dusk, fitted black sweater, mixed blue window light and warm tungsten lamps",
 "city-cafe":"seated at a refined sidewalk cafe, cream blouse and tailored dark trousers, late afternoon natural light",
}
NEGATIVE="different person, changed facial structure, cartoon, anime, illustration, CGI, doll, child, teenager, deformed, distorted face, duplicate person, extra limbs, blurry, plastic skin, text, watermark"

def load_reference(persona_id="celeste_vale",reference_dir="identity/references"):
 path=Path(reference_dir)/f"{persona_id}.json"
 if not path.is_file(): raise ValueError(f"No canonical identity manifest: {path}")
 data=json.loads(path.read_text()); asset=Path(data["reference_asset"])
 if not asset.is_file(): raise ValueError(f"Canonical identity asset missing: {asset}")
 return data,asset

def scene_prompt(scene,identity_reference=True):
 if scene not in SCENES: raise ValueError("Unknown scene")
 return ("Photorealistic editorial photograph of the exact same original fictional adult woman shown in the supplied reference image. "
         "Preserve her recognizable face geometry, eyes, brows, nose, lips, skin tone and texture, beauty mark, and hair identity. "
         +SCENES[scene]+". Camera pulled back several meters: vertical three-quarter-body editorial photograph framed from head through below the knees, both hands visible when natural, substantial environment visible around her, subject occupying roughly half the frame. Do not reproduce the close-up/headshot composition of the reference. Natural anatomy, realistic skin, believable 50mm camera optics. Change pose, clothing, camera framing and setting; one woman only.")

def copy_to_shared(asset,persona_id,category="scenes"):
 root=os.environ.get("SPICE_SHARED_DIR")
 if root:
  shared_root=Path(root).expanduser()
 else:
  home=Path.home()
  termux_docs=home/"storage"/"documents"
  if not termux_docs.is_dir(): return None
  shared_root=termux_docs/"sh"
 dest=shared_root/persona_id/category/Path(asset).name
 dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(asset,dest)
 return str(dest)

def generate_scene(store,persona_id,scene,output,seed=100,denoise=0.45,server_url=None,reference_dir="identity/references",persona=None):
 ref,asset=load_reference(persona_id,reference_dir); prompt=scene_prompt(scene)
 meta=generate(prompt,output,NEGATIVE,seed=seed,server_url=server_url,denoise_strength=denoise,image=asset,profile="cyberrealistic-v10")
 shared=copy_to_shared(meta["asset_uri"],persona_id,"scenes")
 meta.update({"persona_id":persona_id,"scene":scene,"identity_reference":ref["reference_asset"],"identity_sha256":ref["sha256"],"denoise_strength":None if composition_only else denoise,"composition_only":composition_only,"shared_asset_uri":shared})
 store.record_event("identity_scene_generated",meta)
 if persona is not None:
  meta["candidate_id"]=store.propose(persona,f"identity-scene:{scene}","still","identity-test","identity-retention",meta["asset_uri"],prompt,"local-dream:cyberrealistic-v10",str(meta["request"].get("seed",seed)),0)
 return meta
