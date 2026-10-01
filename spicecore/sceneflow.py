"""Generate controlled scene variations from a canonical identity reference."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from .localdream import generate
from .identitytransfer import transfer
from .localidentity import transfer as local_transfer

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
 if identity_reference:
  identity="Photorealistic editorial photograph of the exact same original fictional adult woman shown in the supplied reference image. Preserve her recognizable face geometry, eyes, brows, nose, lips, skin tone and texture, beauty mark, and hair identity. "
 else:
  identity="Photorealistic editorial photograph of one original fictional adult woman, age 32, warm olive skin, dark brown almond eyes, espresso-brown collarbone-length softly wavy hair, understated gold earrings. "
 return (identity+SCENES[scene]+". Camera pulled back several meters: vertical three-quarter-body editorial photograph framed from head through below the knees, both hands visible when natural, substantial environment visible around her, subject occupying roughly half the frame. Natural anatomy, realistic skin, believable 50mm camera optics. One woman only.")

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

def generate_scene(store,persona_id,scene,output,seed=100,denoise=0.45,server_url=None,reference_dir="identity/references",persona=None,composition_only=False):
 ref,asset=load_reference(persona_id,reference_dir)
 prompt=scene_prompt(scene,not composition_only)
 kwargs={} if composition_only else {"denoise_strength":denoise,"image":asset}
 meta=generate(prompt,output,NEGATIVE,seed=seed,server_url=server_url,profile="cyberrealistic-v10",**kwargs)
 shared=copy_to_shared(meta["asset_uri"],persona_id,"scenes")
 meta.update({"persona_id":persona_id,"scene":scene,"identity_reference":ref["reference_asset"],"identity_sha256":ref["sha256"],"denoise_strength":None if composition_only else denoise,"composition_only":composition_only,"shared_asset_uri":shared})
 store.record_event("identity_scene_generated",meta)
 if persona is not None:
  meta["candidate_id"]=store.propose(persona,f"identity-scene:{scene}","still","identity-test","identity-retention",meta["asset_uri"],prompt,"local-dream:cyberrealistic-v10",str(meta["request"].get("seed",seed)),0)
 return meta


def _write_face_mask(path,width,height,invert=False):
 import struct,zlib
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
 cx,cy=width*0.5,height*0.19; rx,ry=width*0.115,height*0.105
 rows=[]
 for y in range(height):
  row=bytearray()
  for x in range(width):
   inside=((x-cx)/rx)**2+((y-cy)/ry)**2<=1
   value=255 if inside else 0
   if invert: value=255-value
   row.append(value)
  rows.append(b"\x00"+bytes(row))
 def chunk(kind,data): return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
 p.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,0,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(rows),6))+chunk(b"IEND",b""))
 return p

def identity_inpaint(store,persona_id,scene_asset,output,seed=200,denoise=0.55,server_url=None,reference_dir="identity/references",persona=None,invert_mask=False):
 ref,_=load_reference(persona_id,reference_dir)
 source=Path(scene_asset)
 if not source.is_file(): raise ValueError(f"Scene asset missing: {source}")
 raw=source.read_bytes()
 if not raw.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("Identity inpaint currently requires a PNG scene")
 import struct
 width,height=struct.unpack(">II",raw[16:24])
 mask=source.with_name(source.stem+"-face-mask.png")
 _write_face_mask(mask,width,height,invert_mask)
 prompt=("Photorealistic face of Celeste Vale, original fictional adult woman age 32: warm olive skin with natural texture and faint freckles, dark brown almond eyes, slightly asymmetric arched brows, straight softly rounded nose, natural full lips, small beauty mark on her left cheek (viewer right), espresso-brown softly wavy hair. Preserve the existing body, pose, clothing, lighting, camera framing and background exactly; change only the masked face/head region.")
 meta=generate(prompt,output,NEGATIVE,seed=seed,server_url=server_url,denoise_strength=denoise,image=source,mask=mask,profile="cyberrealistic-v10")
 shared=copy_to_shared(meta["asset_uri"],persona_id,"identity-inpaint")
 shared_mask=copy_to_shared(mask,persona_id,"identity-inpaint")
 meta.update({"persona_id":persona_id,"identity_reference":ref["reference_asset"],"identity_sha256":ref["sha256"],"source_scene":str(source),"face_mask":str(mask),"shared_mask_uri":shared_mask,"shared_asset_uri":shared,"denoise_strength":denoise,"invert_mask":invert_mask})
 store.record_event("identity_inpaint_generated",meta)
 if persona is not None:
  meta["candidate_id"]=store.propose(persona,"identity-inpaint","still","identity-test","identity-retention",meta["asset_uri"],prompt,"local-dream:cyberrealistic-v10",str(meta["request"].get("seed",seed)),0)
 return meta


def transfer_identity(store,persona_id,scene_asset,output,endpoint=None,strength=0.85,reference_dir="identity/references",persona=None):
 ref,reference=load_reference(persona_id,reference_dir)
 meta=transfer(reference,scene_asset,output,endpoint=endpoint,strength=strength)
 shared=copy_to_shared(meta["asset_uri"],persona_id,"identity-transfer")
 meta.update({"persona_id":persona_id,"identity_reference":ref["reference_asset"],"identity_sha256":ref["sha256"],"source_scene":str(scene_asset),"shared_asset_uri":shared})
 store.record_event("identity_transfer_generated",meta)
 if persona is not None:
  meta["candidate_id"]=store.propose(persona,"identity-transfer","still","identity-test","identity-retention",meta["asset_uri"],"Canonical identity transfer preserving target composition","identity-http","",0)
 return meta


def transfer_identity_local(store,persona_id,scene_asset,output,command=None,reference_dir="identity/references",persona=None):
 ref,reference=load_reference(persona_id,reference_dir)
 meta=local_transfer(reference,scene_asset,output,command=command)
 shared=copy_to_shared(meta["asset_uri"],persona_id,"identity-transfer")
 meta.update({"persona_id":persona_id,"identity_reference":ref["reference_asset"],"identity_sha256":ref["sha256"],"source_scene":str(scene_asset),"shared_asset_uri":shared})
 store.record_event("identity_transfer_generated",meta)
 if persona is not None:
  meta["candidate_id"]=store.propose(persona,"identity-transfer","still","identity-test","identity-retention",meta["asset_uri"],"Local canonical identity transfer preserving target composition","identity-local","",0)
 return meta
