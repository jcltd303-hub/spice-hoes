#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONA="${PERSONA:-lila_hart}"
CROPS_DIR="${CROPS_DIR:-data/canon-face-crops/$PERSONA}"
TRAIN_ROOT="${TRAIN_ROOT:-data/lora-training/$PERSONA}"
BUNDLE_ROOT="${BUNDLE_ROOT:-artifacts/lora-training}"
BUNDLE_DIR="$BUNDLE_ROOT/${PERSONA}-gpu"
ARCHIVE="$BUNDLE_ROOT/${PERSONA}-gpu.tar.gz"

if [[ ! -d "$CROPS_DIR" ]]; then
  echo "missing Canon crop directory: $CROPS_DIR" >&2
  exit 2
fi

count="$(find "$CROPS_DIR" -maxdepth 1 -type f -name 'canon-face-*.png' | wc -l | tr -d ' ')"
if (( count < 4 )); then
  echo "need at least 4 Canon face crops; found $count in $CROPS_DIR" >&2
  exit 3
fi

echo "==> preparing LoRA dataset for $PERSONA from $count Canon crops"
python3 scripts/prepare-lora.py   --persona "$PERSONA"   --face-crops "$CROPS_DIR"

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

cp -a "$TRAIN_ROOT/images" "$BUNDLE_DIR/images"
cp "$TRAIN_ROOT/manifest.json" "$BUNDLE_DIR/manifest.json"
cp scripts/train-persona-lora.sh "$BUNDLE_DIR/train-persona-lora.sh"
cp requirements-lora.txt "$BUNDLE_DIR/requirements-lora.txt"

cat > "$BUNDLE_DIR/README.txt" <<EOF
Spice Hoes persona LoRA GPU bundle

Persona: $PERSONA
Training images: $count

On a CUDA Linux GPU host:

  python3 -m venv .venv-lora
  source .venv-lora/bin/activate
  pip install -r requirements-lora.txt
  accelerate config default

Copy this bundle into the spice-hoes repo at:
  data/lora-training/$PERSONA/

Or from the spice-hoes repo, set TRAIN_DIR to this bundle's images directory:

  PERSONA=$PERSONA \
  TRAIN_DIR=/absolute/path/to/${PERSONA}-gpu/images \
  STEPS=1200 \
  RANK=32 \
  bash scripts/train-persona-lora.sh

Expected output:
  artifacts/loras/$PERSONA.safetensors
EOF

mkdir -p "$BUNDLE_ROOT"
rm -f "$ARCHIVE"
tar -C "$BUNDLE_ROOT" -czf "$ARCHIVE" "${PERSONA}-gpu"

echo "==> saved GPU bundle"
echo "$ARCHIVE"
echo "==> contents"
tar -tzf "$ARCHIVE"
