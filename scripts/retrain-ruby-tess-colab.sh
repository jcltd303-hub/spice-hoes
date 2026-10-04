#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA_ROOT="${DATA_ROOT:-/content/lora-data}"
DRIVE_ROOT="${DRIVE_ROOT:-/content/drive/MyDrive/spice-hoes}"
CANDIDATE_DIR="${CANDIDATE_DIR:-$DRIVE_ROOT/loras-v2}"

mkdir -p "$CANDIDATE_DIR" artifacts/loras-v2

for PERSONA in ruby_wren tess_wilder; do
  echo
  echo "=== PREP $PERSONA ==="

  rm -rf "data/lora-training/$PERSONA"

  python3 scripts/prepare-lora.py     --persona "$PERSONA"     --reference-root "$DATA_ROOT/references"     --face-crops "$DATA_ROOT/canon-face-crops/$PERSONA"     --include-canon

  echo
  echo "=== TRAIN $PERSONA ==="

  PERSONA="$PERSONA"   TRAIN_ROOT="data/lora-training/$PERSONA"   ARTIFACT_DIR="artifacts/loras-v2"   STEPS="${STEPS:-700}"   RANK="${RANK:-16}"   RESOLUTION="${RESOLUTION:-768}"   ACCUM_STEPS="${ACCUM_STEPS:-1}"   bash scripts/train-persona-lora.sh

  cp -f "artifacts/loras-v2/$PERSONA.safetensors" "$CANDIDATE_DIR/$PERSONA.safetensors"
  ls -lh "$CANDIDATE_DIR/$PERSONA.safetensors"
done

echo
echo "READY: $CANDIDATE_DIR"
