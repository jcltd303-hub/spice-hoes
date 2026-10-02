#!/usr/bin/env python3
import argparse, hashlib, json, shutil
from pathlib import Path
from PIL import Image

EXTS={".png",".jpg",".jpeg",".webp"}

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona",default="celeste_vale")
    ap.add_argument("--token",default="cvceleste")
    ap.add_argument("--reference-root",default="data/references")
    ap.add_argument("--reference-dir",default="")
    ap.add_argument("--output-root",default="data/embedding-training")
    ap.add_argument("--min-images",type=int,default=4)
    args=ap.parse_args()

    src=Path(args.reference_dir) if args.reference_dir else Path(args.reference_root)/args.persona
    out=Path(args.output_root)/args.persona
    images=out/"images"
    if not src.exists(): raise SystemExit(f"missing reference directory: {src}")
    images.mkdir(parents=True,exist_ok=True)

    refs=[]
    for p in sorted(src.iterdir()):
        if not p.is_file() or p.suffix.lower() not in EXTS: continue
        n=p.name.lower()
        if n.startswith("master_") or n.startswith("contact_") or "_rear" in n: continue
        try:
            with Image.open(p) as im:
                w,h=im.size
                if min(w,h)<256: continue
        except Exception:
            continue
        refs.append(p)

    if len(refs)<args.min_images:
        raise SystemExit(f"need at least {args.min_images} usable refs; found {len(refs)} in {src}")

    records=[]
    for i,p in enumerate(refs,1):
        dst=images/f"{i:03d}{p.suffix.lower()}"
        shutil.copy2(p,dst)
        with Image.open(dst) as im: size=list(im.size)
        records.append({
            "source":str(p),
            "training_image":str(dst),
            "sha256":sha256(dst),
            "size":size,
        })

    manifest={
        "schema":"spice.textual-inversion.dataset.v1",
        "persona_id":args.persona,
        "token":args.token,
        "format":"sd15-textual-inversion",
        "embedding_width":768,
        "recommended_num_vectors":4,
        "initializer_token":"woman",
        "images":records,
        "notes":[
            "Only verified forward/three-quarter identity references should be used.",
            "No synthetic crop duplication is created; training repeats provide exposure without inventing extra identity evidence.",
        ],
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"ok":True,"images":len(records),"manifest":str(out/"manifest.json")},indent=2))

if __name__=="__main__": main()
