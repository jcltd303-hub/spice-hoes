#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRIVE_ROOT="${DRIVE_ROOT:-/content/drive/MyDrive/spice-hoes/mobile-sdcpp}"
MODEL_REPO="${MODEL_REPO:-stabilityai/stable-diffusion-xl-base-1.0}"
MODEL_FILE="${MODEL_FILE:-sd_xl_base_1.0.safetensors}"
MODEL_TYPE="${MODEL_TYPE:-q5_1}"
SDCPP_COMMIT="${SDCPP_COMMIT:-c3352fb512b2a39737974dabd2100f79e96cddc0}"
SDCPP_SRC="${SDCPP_SRC:-/content/stable-diffusion.cpp}"
SDCPP_BUILD="${SDCPP_BUILD:-/content/stable-diffusion.cpp-build}"
HF_CACHE="${HF_CACHE:-/content/hf-cache}"

mkdir -p "$DRIVE_ROOT/loras" "$DRIVE_ROOT/model"

echo "==> normalize five LoRAs for stable-diffusion.cpp"
python3 scripts/export-loras-for-sdcpp.py   --input-dir artifacts/loras   --output-dir artifacts/loras-sdcpp
cp -f artifacts/loras-sdcpp/*.safetensors "$DRIVE_ROOT/loras/"

if [[ ! -x "$SDCPP_BUILD/bin/sd-cli" ]]; then
  echo "==> build stable-diffusion.cpp converter"
  rm -rf "$SDCPP_SRC" "$SDCPP_BUILD"
  git clone https://github.com/happyyzy/stable-diffusion.cpp.git "$SDCPP_SRC"
  git -C "$SDCPP_SRC" checkout "$SDCPP_COMMIT"
  git -C "$SDCPP_SRC" submodule update --init --recursive
  cmake -S "$SDCPP_SRC" -B "$SDCPP_BUILD"     -DCMAKE_BUILD_TYPE=Release     -DSD_BUILD_EXAMPLES=ON     -DSD_WEBP=OFF     -DSD_WEBM=OFF
  cmake --build "$SDCPP_BUILD" --target sd-cli -j2
fi

BASE="$DRIVE_ROOT/model/sdxl-base-$MODEL_TYPE.gguf"
if [[ ! -s "$BASE" ]]; then
  echo "==> download SDXL base single-file checkpoint"
  python3 - "$MODEL_REPO" "$MODEL_FILE" "$HF_CACHE" <<'PY'
import sys
from huggingface_hub import hf_hub_download
repo, filename, cache = sys.argv[1:4]
print(hf_hub_download(repo_id=repo, filename=filename, cache_dir=cache))
PY
  INPUT="$(python3 - "$MODEL_REPO" "$MODEL_FILE" "$HF_CACHE" <<'PY'
import sys
from huggingface_hub import hf_hub_download
repo, filename, cache = sys.argv[1:4]
print(hf_hub_download(repo_id=repo, filename=filename, cache_dir=cache))
PY
)"
  echo "==> quantize SDXL base -> $MODEL_TYPE"
  "$SDCPP_BUILD/bin/sd-cli"     -M convert     -m "$INPUT"     --type "$MODEL_TYPE"     -o "$BASE"
else
  echo "==> reuse existing $BASE"
fi

echo "==> mobile stable-diffusion.cpp payload ready"
find "$DRIVE_ROOT" -maxdepth 2 -type f -printf '%p %k KB\n' | sort
