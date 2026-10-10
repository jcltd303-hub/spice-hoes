#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
SPICE_TASK_OVERRIDES=()
for SPICE_TASK_KEY in SPICE_LLM_MODEL SPICE_LLM_GPU_LAYERS SPICE_LLM_DEVICE SPICE_LLM_BIN SPICE_LLM_CONTEXT SPICE_LLM_LIB_DIR; do
  if [[ -v "$SPICE_TASK_KEY" ]]; then
    SPICE_TASK_OVERRIDES+=("$SPICE_TASK_KEY=${!SPICE_TASK_KEY}")
  fi
done
for SPICE_TASK_ENV in .env.swarm .env.s24; do
  if [[ -f "$SPICE_TASK_ENV" ]]; then
    set -a
    source "$SPICE_TASK_ENV"
    set +a
  fi
done
for SPICE_TASK_OVERRIDE in "${SPICE_TASK_OVERRIDES[@]}"; do
  export "$SPICE_TASK_OVERRIDE"
done
SPICE_TASK_MODEL="${SPICE_LLM_MODEL:-}"
[[ -f "$SPICE_TASK_MODEL" ]] || { echo 'Set SPICE_LLM_MODEL to an installed GGUF file.' >&2; exit 2; }
SPICE_TASK_BIN="${SPICE_LLM_BIN:-}"
if [[ -z "$SPICE_TASK_BIN" ]]; then
  if [[ -x runtime/llama-snapdragon/bin/llama-server ]]; then
    SPICE_TASK_BIN="$SPICE_TASK_ROOT/runtime/llama-snapdragon/bin/llama-server"
  else
    SPICE_TASK_BIN="$(command -v llama-server || true)"
  fi
fi
[[ -x "$SPICE_TASK_BIN" ]] || { echo 'Install llama-cpp or the Snapdragon artifact first.' >&2; exit 2; }
SPICE_TASK_LIB="${SPICE_LLM_LIB_DIR:-$SPICE_TASK_ROOT/runtime/llama-snapdragon/lib}"
if [[ -d "$SPICE_TASK_LIB" ]]; then
  export LD_LIBRARY_PATH="$SPICE_TASK_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}:/vendor/lib64:/system/lib64"
  export ADSP_LIBRARY_PATH="$SPICE_TASK_LIB;/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/dsp"
  export DSP_LIBRARY_PATH="$ADSP_LIBRARY_PATH"
fi
SPICE_TASK_LAYERS="${SPICE_LLM_GPU_LAYERS:-99}"
SPICE_TASK_DEVICES="$("$SPICE_TASK_BIN" --list-devices 2>&1)"
printf '%s\n' "$SPICE_TASK_DEVICES"
SPICE_TASK_DEVICE="${SPICE_LLM_DEVICE:-}"
if [[ "$SPICE_TASK_LAYERS" != 0 && -z "$SPICE_TASK_DEVICE" ]]; then
  SPICE_TASK_DEVICE="$(printf '%s\n' "$SPICE_TASK_DEVICES" | sed -nE 's/^[[:space:]]*(HTP[[:alnum:]:_-]*|Vulkan[0-9]+|GPUOpenCL[[:alnum:]:_-]*):[[:space:]].*/\1/p' | head -1)"
  [[ -n "$SPICE_TASK_DEVICE" ]] || {
    echo 'No GPU/NPU device reported. Check the backend/driver or explicitly set SPICE_LLM_GPU_LAYERS=0 for CPU.' >&2
    exit 3
  }
fi
SPICE_TASK_ARGS=(--model "$SPICE_TASK_MODEL" --alias "${MOA_MODEL:-spice-local}"
  --host 127.0.0.1 --port "${SPICE_LLM_PORT:-8083}" --ctx-size "${SPICE_LLM_CONTEXT:-4096}"
  --parallel 1 --threads "${SPICE_LLM_THREADS:-4}" --batch-size 128
  --ubatch-size 64 --n-gpu-layers "$SPICE_TASK_LAYERS")
[[ -z "$SPICE_TASK_DEVICE" ]] || SPICE_TASK_ARGS+=(--device "$SPICE_TASK_DEVICE")
echo 'Starting local model; keep this Termux session or supervise it with your service manager.'
exec "$SPICE_TASK_BIN" "${SPICE_TASK_ARGS[@]}"
