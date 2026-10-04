#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONAS=(zara_voss ruby_wren tess_wilder celeste_vale lila_hart)
DATA_ROOT="${DATA_ROOT:-/content/lora-data}"
MAX_PARALLEL="${MAX_PARALLEL:-1}"
STEPS="${STEPS:-1200}"
RANK="${RANK:-32}"
RESOLUTION="${RESOLUTION:-1024}"

gpu_count="$(python3 - <<'PY'
try:
    import torch
    print(torch.cuda.device_count())
except Exception:
    print(0)
PY
)"

if (( gpu_count < 1 )); then
  echo "No CUDA GPU found" >&2
  exit 2
fi

if (( MAX_PARALLEL > gpu_count )); then
  echo "Requested MAX_PARALLEL=$MAX_PARALLEL but only $gpu_count CUDA GPU(s) found." >&2
  echo "Use one trainer per GPU; parallel SDXL trainers on one GPU duplicate the base model and usually OOM." >&2
  MAX_PARALLEL="$gpu_count"
fi

echo "==> GPUs: $gpu_count"
echo "==> parallel trainers: $MAX_PARALLEL"
echo "==> steps=$STEPS rank=$RANK resolution=$RESOLUTION"

pids=()
names=()

wait_one() {
  local pid="${pids[0]}"
  local name="${names[0]}"
  if wait "$pid"; then
    echo "==> finished $name"
  else
    echo "Training failed for $name" >&2
    exit 1
  fi
  pids=("${pids[@]:1}")
  names=("${names[@]:1}")
}

slot=0
for p in "${PERSONAS[@]}"; do
  train_dir="$DATA_ROOT/${p}-gpu/images"
  if [[ ! -d "$train_dir" ]]; then
    echo "Missing prepared dataset: $train_dir" >&2
    exit 3
  fi

  while (( ${#pids[@]} >= MAX_PARALLEL )); do
    wait_one
  done

  gpu=$((slot % gpu_count))
  slot=$((slot + 1))
  echo "==> starting $p on CUDA:$gpu"
  (
    export CUDA_VISIBLE_DEVICES="$gpu"
    PERSONA="$p"     TRAIN_DIR="$train_dir"     STEPS="$STEPS"     RANK="$RANK"     RESOLUTION="$RESOLUTION"     bash scripts/train-persona-lora.sh
  ) >"train-${p}.log" 2>&1 &
  pids+=("$!")
  names+=("$p")
done

while (( ${#pids[@]} )); do
  wait_one
done

echo "==> LoRAs:"
find artifacts/loras -maxdepth 1 -type f -name '*.safetensors' -print | sort
