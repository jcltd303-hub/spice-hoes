"""Production HTTP adapter for xororz/local-dream on Android."""
from __future__ import annotations
import base64,json,os,time
from pathlib import Path
from urllib.request import Request,urlopen

DEFAULT_URL=os.environ.get("LOCAL_DREAM_URL","http://127.0.0.1:8081")
PROFILES={
 "sdxl-dmd2-fast":{"scheduler":"lcm","steps":8,"cfg":1.0,"aspect_ratio":"9:16"},
 "sdxl-quality":{"scheduler":"dpm_karras","steps":25,"cfg":6.0,"aspect_ratio":"9:16"},
 "sd15-quality":{"scheduler":"DPM++ 2M Karras","steps":25,"cfg":6.0,"width":512,"height":768},
}

def _post_json(path,payload,server_url=None,timeout=900,accept="application/json"):
 req=Request((server_url or DEFAULT_URL).rstrip("/")+path,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":accept},method="POST")
 return urlopen(req,timeout=timeout)

def tokenize(prompt,server_url=None,timeout=30):
 with _post_json("/tokenize",{"prompt":prompt},server_url,timeout) as r:
  return json.loads(r.read().decode())

def generate(prompt,output,negative_prompt="",size=None,steps=None,cfg=None,seed=None,server_url=None,timeout=900,
             width=None,height=None,scheduler=None,aspect_ratio=None,image=None,mask=None,denoise_strength=None,
             use_opencl=None,profile=None):
 settings=dict(PROFILES.get(profile,{}))
 width=width or settings.get("width"); height=height or settings.get("height")
 payload={"prompt":prompt,"negative_prompt":negative_prompt,
          "steps":steps if steps is not None else settings.get("steps",8),
          "cfg":cfg if cfg is not None else settings.get("cfg",1.0)}
 if size is not None: payload["size"]=size
 if width is not None: payload["width"]=int(width)
 if height is not None: payload["height"]=int(height)
 scheduler=scheduler or settings.get("scheduler")
 if scheduler: payload["scheduler"]=scheduler
 aspect_ratio=aspect_ratio or settings.get("aspect_ratio")
 if aspect_ratio: payload["aspect_ratio"]=aspect_ratio
 if seed is not None: payload["seed"]=int(seed)
 if image is not None: payload["image"]=image
 if mask is not None: payload["mask"]=mask
 if denoise_strength is not None: payload["denoise_strength"]=float(denoise_strength)
 if use_opencl is not None: payload["use_opencl"]=bool(use_opencl)
 started=time.monotonic(); complete=None; progress=[]
 with _post_json("/generate",payload,server_url,timeout,"text/event-stream") as response:
  for raw in response:
   line=raw.decode("utf-8").strip()
   if not line.startswith("data: "): continue
   data=line[6:]
   if data=="[DONE]": break
   msg=json.loads(data)
   if msg.get("type")=="complete": complete=msg
   elif msg.get("type")=="progress": progress.append({k:msg.get(k) for k in ("step","total_steps")})
 if not complete or "image" not in complete: raise RuntimeError("Local Dream ended without a complete image event")
 width,height,channels=(int(complete[k]) for k in ("width","height","channels"))
 pixels=base64.b64decode(complete["image"]); expected=width*height*channels
 if len(pixels)!=expected: raise RuntimeError(f"Local Dream image payload length {len(pixels)} != {expected}")
 out=Path(output); out.parent.mkdir(parents=True,exist_ok=True); _write_png(out,width,height,channels,pixels)
 return {"asset_uri":str(out),"provider":"local-dream","profile":profile,"server_url":server_url or DEFAULT_URL,
         "request":payload,"width":width,"height":height,"channels":channels,"progress":progress,
         "generation_time_ms":complete.get("generation_time_ms"),"round_trip_ms":round((time.monotonic()-started)*1000)}

def _write_png(path,width,height,channels,pixels):
 import struct,zlib
 if channels not in (3,4): raise RuntimeError("Only RGB/RGBA Local Dream output is supported")
 color=2 if channels==3 else 6
 rows=b"".join(b"\x00"+pixels[y*width*channels:(y+1)*width*channels] for y in range(height))
 def chunk(kind,data): return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
 path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,color,0,0,0))+chunk(b"IDAT",zlib.compress(rows,6))+chunk(b"IEND",b""))
