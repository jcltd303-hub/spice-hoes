#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONA="${PERSONA:-lila_hart}"
case "$PERSONA" in
  zara_voss) TOKEN="${TOKEN:-spzara}" ;;
  ruby_wren) TOKEN="${TOKEN:-spruby}" ;;
  tess_wilder) TOKEN="${TOKEN:-sptess}" ;;
  celeste_vale) TOKEN="${TOKEN:-spceleste}" ;;
  lila_hart) TOKEN="${TOKEN:-splila}" ;;
  *) echo "unsupported persona: $PERSONA" >&2; exit 2 ;;
esac

BASE_MODEL="${BASE_MODEL:-stabilityai/stable-diffusion-xl-base-1.0}"
TRAIN_ROOT="${TRAIN_ROOT:-data/lora-training/$PERSONA}"
TRAIN_DIR="${TRAIN_DIR:-$TRAIN_ROOT/images}"
OUT_DIR="${OUT_DIR:-$TRAIN_ROOT/output}"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/loras}"
DIFFUSERS_REF="${DIFFUSERS_REF:-v0.35.1}"
STEPS="${STEPS:-1200}"
LR="${LR:-1e-4}"
RANK="${RANK:-32}"
SEED="${SEED:-20261004}"
RESOLUTION="${RESOLUTION:-1024}"

python3 - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("CUDA GPU required. Run this trainer in Colab/Kaggle/Azure GPU, not Termux.")
print("CUDA:", torch.cuda.get_device_name(0))
PY

if [[ -d "$TRAIN_DIR" ]] && find "$TRAIN_DIR" -type f -name '*.jpg' -print -quit | grep -q .; then
  echo "==> using prebuilt LoRA dataset: $TRAIN_DIR"
else
  if [[ ! -d "data/canon-face-crops/$PERSONA" ]] || ! find "data/canon-face-crops/$PERSONA" -type f -name 'canon-face-*.png' -print -quit | grep -q .; then
    PERSONA="$PERSONA" bash scripts/extract-canon-faces.sh
  fi
  python3 scripts/prepare-lora.py --persona "$PERSONA" --face-crops "data/canon-face-crops/$PERSONA"
fi

COUNT="$(find "$TRAIN_DIR" -maxdepth 1 -type f -name '*.jpg' | wc -l | tr -d ' ')"
if (( COUNT < 4 )); then
  echo "Need at least 4 Canon-derived training images; got $COUNT" >&2
  echo "Run scripts/extract-canon-faces.sh first." >&2
  exit 3
fi

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/spice-diffusers"
SRC="$CACHE/diffusers-$DIFFUSERS_REF"
if [[ ! -f "$SRC/examples/advanced_diffusion_training/train_dreambooth_lora_sdxl.py" ]]; then
  rm -rf "$SRC"
  mkdir -p "$CACHE"
  git clone --depth 1 --branch "$DIFFUSERS_REF" https://github.com/huggingface/diffusers.git "$SRC"
fi

mkdir -p "$OUT_DIR" "$ARTIFACT_DIR"

accelerate launch "$SRC/examples/advanced_diffusion_training/train_dreambooth_lora_sdxl.py" \
  --pretrained_model_name_or_path="$BASE_MODEL" \
  --instance_data_dir="$TRAIN_DIR" \
  --output_dir="$OUT_DIR" \
  --instance_prompt="photo of $TOKEN woman, fictional adult woman" \
  --resolution="$RESOLUTION" \
  --train_batch_size=1 \
  --gradient_accumulation_steps=4 \
  --gradient_checkpointing \
  --use_8bit_adam \
  --learning_rate="$LR" \
  --lr_scheduler=constant \
  --lr_warmup_steps=0 \
  --max_train_steps="$STEPS" \
  --rank="$RANK" \
  --mixed_precision=fp16 \
  --seed="$SEED" \
  --checkpointing_steps=300

FOUND="$(find "$OUT_DIR" -type f -name '*.safetensors' | sort | tail -n1 || true)"
if [[ -z "$FOUND" ]]; then
  echo "No LoRA safetensors produced in $OUT_DIR" >&2
  exit 4
fi

DEST="$ARTIFACT_DIR/${PERSONA}.safetensors"
cp "$FOUND" "$DEST"
python3 - "$DEST" "$PERSONA" "$TOKEN" <<'PY'
import sys
from safetensors import safe_open
path, persona, token = sys.argv[1:4]
with safe_open(path, framework="pt", device="cpu") as f:
    keys=list(f.keys())
    if not keys: raise SystemExit("LoRA contains no tensors")
    print({"artifact":path,"persona":persona,"token":token,"tensor_count":len(keys)})
PY

echo "READY: $DEST"
echo "TRIGGER: $TOKEN"
