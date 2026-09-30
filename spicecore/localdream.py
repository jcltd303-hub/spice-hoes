"""HTTP adapter for xororz/local-dream running on the Android device."""
from __future__ import annotations
import base64,json,os,time
from pathlib import Path
from urllib.request import Request,urlopen

DEFAULT_URL=os.environ.get("LOCAL_DREAM_URL","http://127.0.0.1:8081")

def generate(prompt,output,negative_prompt="",size=1024,steps=8,cfg=1.0,seed=None,server_url=None,timeout=900):
    payload={"prompt":prompt,"negative_prompt":negative_prompt,"size":size,"steps":steps,"cfg":cfg}
    if seed is not None: payload["seed"]=int(seed)
    req=Request((server_url or DEFAULT_URL).rstrip("/")+"/generate",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":"text/event-stream"},method="POST")
    started=time.monotonic(); complete=None
    with urlopen(req,timeout=timeout) as response:
        for raw in response:
            line=raw.decode("utf-8").strip()
            if not line.startswith("data: "): continue
            data=line[6:]
            if data=="[DONE]": break
            msg=json.loads(data)
            if msg.get("type")=="complete": complete=msg
    if not complete or "image" not in complete: raise RuntimeError("Local Dream ended without a complete image event")
    width,height,channels=(int(complete[k]) for k in ("width","height","channels"))
    pixels=base64.b64decode(complete["image"])
    expected=width*height*channels
    if len(pixels)!=expected: raise RuntimeError(f"Local Dream image payload length {len(pixels)} != {expected}")
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    _write_png(out,width,height,channels,pixels)
    return {"asset_uri":str(out),"provider":"local-dream","server_url":server_url or DEFAULT_URL,"request":payload,"width":width,"height":height,"channels":channels,"generation_time_ms":complete.get("generation_time_ms"),"round_trip_ms":round((time.monotonic()-started)*1000)}

def _write_png(path,width,height,channels,pixels):
    import struct,zlib
    if channels not in (3,4): raise RuntimeError("Only RGB/RGBA Local Dream output is supported")
    color=2 if channels==3 else 6
    rows=b"".join(b"\x00"+pixels[y*width*channels:(y+1)*width*channels] for y in range(height))
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    png=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,color,0,0,0))+chunk(b"IDAT",zlib.compress(rows,6))+chunk(b"IEND",b"")
    path.write_bytes(png)
