"""Generate controlled scene variations from a canonical identity reference."""
from __future__ import annotations
import json
from pathlib import Path
from .localdream import generate

SCENES={
 "hotel-lobby":"standing in an elegant boutique hotel lobby, tailored burgundy jacket, reviewing fabric samples, warm practical lamps and soft window light, three-quarter editorial portrait",
 "record-shop":"browsing jazz records at dusk, fitted black sweater, mixed blue window light and warm tungsten lamps, candid three-quarter portrait",
 "city-cafe":"seated at a refined sidewalk cafe, cream blouse and tailored dark trousers, late afternoon natural light, relaxed candid portrait",
}
NEGATIVE="different person, changed facial structure, cartoon, anime, illustration, CGI, doll, child, teenager, deformed, distorted face, duplicate person, extra limbs, blurry, plastic skin, text, watermark"

def load_reference(persona_id="celeste_vale",reference_dir="identity/references"):
 path=Path(reference_dir)/f"{persona_id}.json"
 if not path.is_file(): raise ValueError(f"No canonical identity manifest: {path}")
 data=json.loads(path.read_text()); asset=Path(data["reference_asset"])
 if not asset.is_file(): raise ValueError(f"Canonical identity asset missing: {asset}")
 return data,asset

def scene_prompt(scene):
 if scene not in SCENES: raise ValueError("Unknown scene")
 return ("Photorealistic editorial photograph of the exact same original fictional adult woman shown in the supplied reference image. "
         "Preserve her recognizable face geometry, eyes, brows, nose, lips, skin tone and texture, beauty mark, and hair identity. "
         +SCENES[scene]+". Natural anatomy, realistic skin, believable camera optics. Change only pose, clothing and setting; one woman only.")

def generate_scene(store,persona_id,scene,output,seed=100,denoise=0.35,server_url=None,reference_dir="identity/references",persona=None):
 ref,asset=load_reference(persona_id,reference_dir); prompt=scene_prompt(scene)
 meta=generate(prompt,output,NEGATIVE,seed=seed,server_url=server_url,denoise_strength=denoise,
               image=asset,profile="cyberrealistic-v10")
 meta.update({"persona_id":persona_id,"scene":scene,"identity_reference":ref["reference_asset"],
              "identity_sha256":ref["sha256"],"denoise_strength":denoise})
 store.record_event("identity_scene_generated",meta)
 return meta
