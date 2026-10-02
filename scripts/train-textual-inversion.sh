#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONA="${PERSONA:-celeste_vale}"
TOKEN="${TOKEN:-cvceleste}"
BASE_MODEL="${BASE_MODEL:-stable-diffusion-v1-5/stable-diffusion-v1-5}"
TRAIN_DIR="${TRAIN_DIR:-data/embedding-training/$PERSONA/images}"
OUT_DIR="${OUT_DIR:-data/embedding-training/$PERSONA/output}"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/embeddings}"
DIFFUSERS_REF="${DIFFUSERS_REF:-v0.35.1}"
STEPS="${STEPS:-2000}"
LR="${LR:-5e-4}"
VECTORS="${VECTORS:-4}"
REPEATS="${REPEATS:-100}"
SEED="${SEED:-20261002}"
REFERENCE_DIR="${REFERENCE_DIR:-}"

PREP=(python3 scripts/prepare-textual-inversion.py --persona "$PERSONA" --token "$TOKEN")
if [[ -n "$REFERENCE_DIR" ]]; then PREP+=(--reference-dir "$REFERENCE_DIR"); fi
"${PREP[@]}"

python3 - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA GPU required for practical textual-inversion training")
print("CUDA:", torch.cuda.get_device_name(0))
PY

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/spice-diffusers"
SRC="$CACHE/diffusers-$DIFFUSERS_REF"
if [[ ! -f "$SRC/examples/textual_inversion/textual_inversion.py" ]]; then
  rm -rf "$SRC"
  mkdir -p "$CACHE"
  git clone --depth 1 --branch "$DIFFUSERS_REF" https://github.com/huggingface/diffusers.git "$SRC"
fi

mkdir -p "$OUT_DIR" "$ARTIFACT_DIR"

accelerate launch "$SRC/examples/textual_inversion/textual_inversion.py"   --pretrained_model_name_or_path="$BASE_MODEL"   --train_data_dir="$TRAIN_DIR"   --learnable_property="object"   --placeholder_token="$TOKEN"   --initializer_token="woman"   --num_vectors="$VECTORS"   --resolution=512   --train_batch_size=1   --gradient_accumulation_steps=4   --learning_rate="$LR"   --lr_scheduler="constant"   --lr_warmup_steps=0   --max_train_steps="$STEPS"   --repeats="$REPEATS"   --seed="$SEED"   --mixed_precision="fp16"   --output_dir="$OUT_DIR"

FOUND="$(find "$OUT_DIR" -maxdepth 2 -type f \( -name 'learned_embeds.safetensors' -o -name '*.safetensors' \) | head -n1 || true)"
if [[ -z "$FOUND" ]]; then
  echo "No safetensors embedding produced in $OUT_DIR" >&2
  exit 1
fi

cp "$FOUND" "$ARTIFACT_DIR/$TOKEN.safetensors"

python3 - "$ARTIFACT_DIR/$TOKEN.safetensors" "$TOKEN" "$VECTORS" <<'PY'
import sys
from safetensors import safe_open
path, token, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
with safe_open(path, framework="pt", device="cpu") as f:
    keys=list(f.keys())
    if not keys: raise SystemExit("embedding has no tensors")
    shapes={k:list(f.get_tensor(k).shape) for k in keys}
ok=any(len(s)>=1 and s[-1]==768 and (len(s)==1 or s[0]==expected) for s in shapes.values())
if not ok: raise SystemExit(f"Local Dream incompatible tensor shapes: {shapes}")
print({"artifact":path,"token":token,"keys":keys,"shapes":shapes})
PY

echo "READY: $ARTIFACT_DIR/$TOKEN.safetensors"
