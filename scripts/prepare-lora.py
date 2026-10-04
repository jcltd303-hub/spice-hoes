#!/usr/bin/env python3
import argparse, json, os, shutil
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

PERSONA_TOKENS = {
    "zara_voss": "spzara",
    "ruby_wren": "spruby",
    "tess_wilder": "sptess",
    "celeste_vale": "spceleste",
    "lila_hart": "splila",
}

def canon_files(root: Path, persona: str):
    d = root / persona
    if not d.is_dir():
        raise SystemExit(f"missing Canon directory: {d}")
    out=[]
    for p in sorted(d.iterdir()):
        if not p.is_file(): continue
        stem=p.stem.lower()
        if stem=="canon" or stem.startswith("canon-") or stem.startswith("canon_"):
            if p.suffix.lower() in {".png",".jpg",".jpeg"}:
                out.append(p)
    if not out:
        raise SystemExit(f"no strict Canon images found in {d}")
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona", required=True, choices=sorted(PERSONA_TOKENS))
    ap.add_argument("--reference-root", default="data/references")
    ap.add_argument("--face-crops", default="")
    ap.add_argument("--out-root", default="data/lora-training")
    ap.add_argument("--token", default="")
    args=ap.parse_args()
    persona=args.persona
    token=args.token or PERSONA_TOKENS[persona]
    out=Path(args.out_root)/persona
    images=out/"images"
    if images.exists(): shutil.rmtree(images)
    images.mkdir(parents=True, exist_ok=True)

    sources=[]
    crop_dir=Path(args.face_crops) if args.face_crops else Path("data/canon-face-crops")/persona
    if crop_dir.is_dir():
        sources=[p for p in sorted(crop_dir.iterdir()) if p.suffix.lower() in {".png",".jpg",".jpeg"}]

    if not sources:
        # Fallback only: use strict Canon images directly. The preferred path is
        # scripts/extract-canon-faces.sh, which generates one crop per detected view.
        sources=canon_files(Path(args.reference_root), persona)

    caption=f"photo of {token} woman, fictional adult woman"
    records=[]
    for i, src in enumerate(sources, 1):
        img=Image.open(src).convert("RGB")
        # Preserve composition, standardize orientation, and create one neutral
        # 1024 training image. Do not synthesize identity-changing augmentations.
        img=ImageOps.exif_transpose(img)
        img.thumbnail((1024,1024), Image.Resampling.LANCZOS)
        canvas=Image.new("RGB",(1024,1024),(127,127,127))
        x=(1024-img.width)//2; y=(1024-img.height)//2
        canvas.paste(img,(x,y))
        dst=images/f"{i:02d}.jpg"
        canvas.save(dst, quality=96, subsampling=0)
        (images/f"{i:02d}.txt").write_text(caption+"\n", encoding="utf-8")
        records.append({"source":str(src),"image":str(dst),"caption":caption})

    manifest={
        "persona":persona,
        "token":token,
        "images":len(records),
        "records":records,
        "note":"Identity LoRA training set derived only from strict Canon or Canon face crops.",
    }
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__=="__main__":
    main()
