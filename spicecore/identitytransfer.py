"""Provider-neutral identity transfer adapter.

The endpoint receives the canonical identity image plus a composed target scene.
Configure SPICE_IDENTITY_URL to an InstantID/PuLID/face-swap service you control.
"""
from __future__ import annotations
import base64,hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen

DEFAULT_URL=os.environ.get("SPICE_IDENTITY_URL","")

def _encoded(path):
 data=Path(path).read_bytes()
 if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8")):
  raise ValueError(f"Identity transfer input must be PNG/JPEG: {path}")
 return base64.b64encode(data).decode("ascii"),hashlib.sha256(data).hexdigest()

def transfer(reference_image,target_image,output,endpoint=None,timeout=900,strength=0.85):
 url=(endpoint or DEFAULT_URL).strip()
 if not url: raise ValueError("Set SPICE_IDENTITY_URL or pass --endpoint")
 ref,ref_sha=_encoded(reference_image); target,target_sha=_encoded(target_image)
 payload={"reference_image":ref,"target_image":target,"strength":float(strength),"preserve_composition":True}
 req=Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":"application/json,image/png,image/jpeg"},method="POST")
 with urlopen(req,timeout=timeout) as response:
  body=response.read(); content_type=response.headers.get("Content-Type","").lower()
 if body.startswith(b"\x89PNG\r\n\x1a\n") or body.startswith(b"\xff\xd8"):
  data=body
 else:
  msg=json.loads(body.decode())
  encoded=msg.get("image") or msg.get("output") or msg.get("image_base64")
  if isinstance(encoded,dict): encoded=encoded.get("base64")
  if not encoded: raise RuntimeError("Identity endpoint returned no image")
  if isinstance(encoded,str) and encoded.startswith("data:"): encoded=encoded.split(",",1)[1]
  data=base64.b64decode(encoded)
  if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8")):
   raise RuntimeError("Identity endpoint returned invalid image bytes")
 out=Path(output); out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data)
 return {"asset_uri":str(out),"provider":"identity-http","endpoint":url,"strength":float(strength),"reference_sha256":ref_sha,"target_sha256":target_sha,"response_content_type":content_type}
