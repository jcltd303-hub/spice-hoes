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
    ap.add_argument("--include-canon", action="store_true", help="include strict Canon images alongside extracted face crops")
    ap.add_argument("--expand-single-canon", action="store_true", help="create deterministic mild crop variants when only one Canon image is available")
    args=ap.parse_args()
    persona=args.persona
    token=args.token or PERSONA_TOKENS[persona]
    out=Path(args.out_root)/persona
    images=out/"images"
    if images.exists(): shutil.rmtree(images)
    images.mkdir(parents=True, exist_ok=True)

    sources=[]
    crop_dir=Path(args.face_crops) if args.face_crops else Path("data/canon-face-crops")/persona
    crop_sources=[]
    if crop_dir.is_dir():
        crop_sources=[p for p in sorted(crop_dir.iterdir()) if p.suffix.lower() in {".png",".jpg",".jpeg"}]
        sources.extend(crop_sources)

    if args.include_canon or not sources:
        # Whole Canon frames help prevent a face-only dataset from teaching
        # pathological macro/eye crops. Keep this opt-in because some personas
        # use contact sheets where whole-sheet training is undesirable.
        for p in canon_files(Path(args.reference_root), persona):
            if p not in sources:
                sources.append(p)

    PERSONA_CAPTIONS = {
        "ruby_wren": f"photo of {token} woman, fictional adult woman, age 30, vivid copper-auburn short textured bob with deep side part, fair neutral skin with light freckles, green-hazel upturned almond eyes",
        "tess_wilder": f"photo of {token} woman, fictional adult woman, age 27, dark brown hair tied back cleanly, neutral light-medium freckled skin, gray-green slightly hooded almond eyes, athletic adult facial structure",
    }
    caption=PERSONA_CAPTIONS.get(persona, f"photo of {token} woman, fictional adult woman")
    records=[]

    def write_training_image(img, src, index, variant):
        img=ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((1024,1024), Image.Resampling.LANCZOS)
        canvas=Image.new("RGB",(1024,1024),(127,127,127))
        x=(1024-img.width)//2; y=(1024-img.height)//2
        canvas.paste(img,(x,y))
        dst=images/f"{index:02d}.jpg"
        canvas.save(dst, quality=96, subsampling=0)
        (images/f"{index:02d}.txt").write_text(caption+"\n", encoding="utf-8")
        records.append({"source":str(src),"image":str(dst),"caption":caption,"variant":variant})

    next_index=1
    for src in sources:
        base=Image.open(src).convert("RGB")
        write_training_image(base.copy(), src, next_index, "full")
        next_index += 1

        # A single Canon image is not enough for DreamBooth LoRA training.
        # For Ruby/Tess we create only mild deterministic center crops of the
        # same authoritative pixels. No color/style/face synthesis is used.
        if args.expand_single_canon and len(sources)==1:
            w,h=base.size
            for ratio in (0.96,0.92,0.88,0.84,0.80):
                cw=max(1,int(w*ratio)); ch=max(1,int(h*ratio))
                left=(w-cw)//2; top=(h-ch)//2
                crop=base.crop((left,top,left+cw,top+ch))
                write_training_image(crop, src, next_index, f"center_crop_{ratio:.2f}")
                next_index += 1

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
