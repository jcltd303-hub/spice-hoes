#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONA="${PERSONA:-lila_hart}"
REFERENCE_ROOT="${REFERENCE_ROOT:-data/references}"
OUT_ROOT="${OUT_ROOT:-data/canon-face-crops}"
OUT_DIR="$OUT_ROOT/$PERSONA"
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.png "$OUT_DIR"/*.json 2>/dev/null || true

if [[ -f "$ROOT/.env.spicemedia" ]]; then
  set -a
  source "$ROOT/.env.spicemedia"
  set +a
fi
if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" && -s "$ROOT/models/face/scrfd_10g.bin" ]]; then
  export SPICE_FACE_DETECT_MODEL="$ROOT/models/face/scrfd_10g.bin"
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" && -s "$ROOT/models/face/arcface_w600k_r50.bin" ]]; then
  export SPICE_FACE_EMBED_MODEL="$ROOT/models/face/arcface_w600k_r50.bin"
fi

# Force the lightweight face-only core while extracting crops.
unset SPICE_QNN_MODEL_DIR

mapfile -t refs < <(find "$REFERENCE_ROOT/$PERSONA" -maxdepth 1 -type f \(   -iname 'canon.png' -o -iname 'canon.jpg' -o -iname 'canon.jpeg' -o   -iname 'canon-*.png' -o -iname 'canon-*.jpg' -o -iname 'canon-*.jpeg' -o   -iname 'canon_*.png' -o -iname 'canon_*.jpg' -o -iname 'canon_*.jpeg' \) | sort)

if (( ${#refs[@]} == 0 )); then
  echo "No strict Canon images found for $PERSONA" >&2
  exit 2
fi

n=0
for ref in "${refs[@]}"; do
  b64="$(base64 -w 0 "$ref" 2>/dev/null || base64 "$ref" | tr -d '\n')"
  json="$OUT_DIR/detect-$((n+1)).json"
  printf '{"image_base64":"%s"}' "$b64" | go run ./cmd/spicemedia detect > "$json"

  python3 - "$ref" "$json" "$OUT_DIR" "$n" <<'PY'
import json, sys
from pathlib import Path
from PIL import Image

src=Path(sys.argv[1]); det=Path(sys.argv[2]); out=Path(sys.argv[3]); offset=int(sys.argv[4])
img=Image.open(src).convert("RGB")
data=json.loads(det.read_text())
faces=data.get("faces") or []
W,H=img.size

# The 0.10 SCRFD fallback is intentionally permissive for contact sheets, but
# it can return dozens of tiny false positives. Rank detections by confidence
# and face area, reject implausibly small boxes, then cap each Canon sheet at
# eight views. A six-view sheet should normally yield about six crops, not 49.
candidates=[]
min_side=0.07*min(W,H)
min_area=0.004*W*H
for f in faces:
    box=f.get("box") or []
    if len(box)!=4: continue
    x1,y1,x2,y2=map(float,box)
    fw=max(1.0,x2-x1); fh=max(1.0,y2-y1)
    area=fw*fh
    score=float(f.get("score") or 0.0)
    if min(fw,fh) < min_side or area < min_area:
        continue
    # Favor confident, substantial portrait faces without letting sheer box
    # size overwhelm confidence.
    rank=score*((area/(W*H))**0.25)
    candidates.append((rank,score,area,(x1,y1,x2,y2)))

candidates.sort(reverse=True, key=lambda x:x[0])
candidates=candidates[:8]

written=0
for _,score,area,(x1,y1,x2,y2) in candidates:
    fw=max(1.0,x2-x1); fh=max(1.0,y2-y1)
    cx=(x1+x2)/2; cy=(y1+y2)/2
    # generous portrait crop: hair + shoulders, while preserving the detected face.
    side=max(fw,fh)*3.2
    left=max(0,int(cx-side/2)); top=max(0,int(cy-side*0.46))
    right=min(W,int(cx+side/2)); bottom=min(H,int(cy+side*0.54))
    if right-left < 128 or bottom-top < 128: continue
    crop=img.crop((left,top,right,bottom))
    # square-pad without stretching.
    s=max(crop.size)
    canvas=Image.new("RGB",(s,s),(127,127,127))
    canvas.paste(crop,((s-crop.width)//2,(s-crop.height)//2))
    canvas=canvas.resize((1024,1024),Image.Resampling.LANCZOS)
    dst=out/f"canon-face-{offset+written+1:02d}.png"
    canvas.save(dst)
    written+=1

print(json.dumps({
    "raw_detections": len(faces),
    "accepted_crops": written,
    "max_score": max([float(f.get("score") or 0.0) for f in faces], default=0.0),
}))
PY

  count="$(find "$OUT_DIR" -maxdepth 1 -type f -name 'canon-face-*.png' | wc -l | tr -d ' ')"
  n="$count"
done

rm -f "$OUT_DIR"/detect-*.json
echo "Extracted $n Canon face views to $OUT_DIR"
if (( n < 4 )); then
  echo "Warning: only $n faces were extracted; 6-12 varied Canon views is preferable for LoRA training." >&2
fi
