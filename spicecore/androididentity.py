"""Android-accelerated identity service client for Snapdragon devices."""
from __future__ import annotations
import base64,hashlib,json,os
from pathlib import Path
from urllib.request import Request,urlopen

DEFAULT_URL=os.environ.get("SPICE_ANDROID_IDENTITY_URL","http://127.0.0.1:8082")

def _image(path):
 data=Path(path).read_bytes()
 if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8")): raise ValueError(f"Expected PNG/JPEG: {path}")
 return base64.b64encode(data).decode(),hashlib.sha256(data).hexdigest()

def health(endpoint=None,timeout=5):
 url=(endpoint or DEFAULT_URL).rstrip("/")+"/health"
 try:
  with urlopen(url,timeout=timeout) as r: data=json.loads(r.read().decode())
  return {"ready":bool(data.get("ready")),"endpoint":url,**data}
 except Exception as e: return {"ready":False,"endpoint":url,"error":f"{type(e).__name__}: {e}"}

def transfer(reference,target,output,endpoint=None,timeout=900):
 base=(endpoint or DEFAULT_URL).rstrip("/")
 ref,ref_sha=_image(reference); dst,dst_sha=_image(target)
 payload={"reference_image":ref,"target_image":dst,"preserve_composition":True}
 req=Request(base+"/transfer",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":"application/json,image/png,image/jpeg"},method="POST")
 with urlopen(req,timeout=timeout) as r: body=r.read(); ct=r.headers.get("Content-Type","")
 if body.startswith(b"\x89PNG\r\n\x1a\n") or body.startswith(b"\xff\xd8"): data=body
 else:
  msg=json.loads(body.decode()); encoded=msg.get("image") or msg.get("image_base64")
  if isinstance(encoded,str) and encoded.startswith("data:"): encoded=encoded.split(",",1)[1]
  if not encoded: raise RuntimeError("Android identity service returned no image")
  data=base64.b64decode(encoded)
 out=Path(output); out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data)
 return {"asset_uri":str(out),"provider":"identity-android","endpoint":base,"reference_sha256":ref_sha,"target_sha256":dst_sha,"response_content_type":ct}
