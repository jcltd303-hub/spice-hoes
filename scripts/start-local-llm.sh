#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
SPICE_TASK_OVERRIDES=()
for SPICE_TASK_KEY in SPICE_LLM_MODEL SPICE_LLM_BACKEND SPICE_LLM_GPU_LAYERS SPICE_LLM_DEVICE SPICE_LLM_BIN SPICE_LLM_CONTEXT SPICE_LLM_LIB_DIR SPICE_LLM_PORT SPICE_LLM_THREADS; do
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
SPICE_TASK_BACKEND="${SPICE_LLM_BACKEND:-auto}"
case "$SPICE_TASK_BACKEND" in
  auto|cpu|opencl|vulkan|hexagon) ;;
  *) echo 'SPICE_LLM_BACKEND must be auto, cpu, opencl, vulkan, or hexagon.' >&2; exit 2 ;;
esac
SPICE_TASK_LAYERS="${SPICE_LLM_GPU_LAYERS:-99}"
SPICE_TASK_DEVICE="${SPICE_LLM_DEVICE:-}"
if [[ "$SPICE_TASK_BACKEND" == cpu || "$SPICE_TASK_LAYERS" == 0 || "$SPICE_TASK_DEVICE" == none ]]; then
  SPICE_TASK_BACKEND=cpu
  SPICE_TASK_LAYERS=0
  SPICE_TASK_DEVICE=none
fi
SPICE_TASK_BIN="${SPICE_LLM_BIN:-}"
if [[ -z "$SPICE_TASK_BIN" ]]; then
  if [[ -x runtime/llama-snapdragon/bin/llama-server ]]; then
    SPICE_TASK_BIN="$SPICE_TASK_ROOT/runtime/llama-snapdragon/bin/llama-server"
  else
    SPICE_TASK_BIN="$(command -v llama-server || true)"
  fi
fi
[[ -x "$SPICE_TASK_BIN" ]] || { echo 'Install llama-cpp or the Snapdragon artifact first.' >&2; exit 2; }
SPICE_TASK_LIB="${SPICE_LLM_LIB_DIR:-}"
if [[ -z "$SPICE_TASK_LIB" && "$SPICE_TASK_BIN" == "$SPICE_TASK_ROOT/runtime/llama-snapdragon/bin/"* ]]; then
  SPICE_TASK_LIB="$SPICE_TASK_ROOT/runtime/llama-snapdragon/lib"
fi
if [[ -n "$SPICE_TASK_LIB" && -d "$SPICE_TASK_LIB" ]]; then
  export LD_LIBRARY_PATH="$SPICE_TASK_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}:/vendor/lib64:/system/lib64"
  export ADSP_LIBRARY_PATH="$SPICE_TASK_LIB;/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/dsp"
  export DSP_LIBRARY_PATH="$ADSP_LIBRARY_PATH"
fi
if [[ "$SPICE_TASK_BACKEND" != cpu ]]; then
  if ! SPICE_TASK_DEVICES="$("$SPICE_TASK_BIN" --list-devices 2>&1)"; then
    printf '%s\n' "$SPICE_TASK_DEVICES" >&2
    echo 'Device probing failed. Recover with SPICE_LLM_BACKEND=cpu bash scripts/start-local-llm.sh.' >&2
    exit 3
  fi
  printf '%s\n' "$SPICE_TASK_DEVICES"
  case "$SPICE_TASK_BACKEND" in
    auto) SPICE_TASK_PATTERNS=('GPUOpenCL[[:alnum:]_-]*' 'HTP[[:alnum:]:_-]*' 'Vulkan[0-9]+') ;;
    opencl) SPICE_TASK_PATTERNS=('GPUOpenCL[[:alnum:]_-]*') ;;
    vulkan) SPICE_TASK_PATTERNS=('Vulkan[0-9]+') ;;
    hexagon) SPICE_TASK_PATTERNS=('HTP[[:alnum:]:_-]*') ;;
  esac
  if [[ -n "$SPICE_TASK_DEVICE" && "$SPICE_TASK_BACKEND" != auto && ! "$SPICE_TASK_DEVICE" =~ ^${SPICE_TASK_PATTERNS[0]}$ ]]; then
    echo 'SPICE_LLM_DEVICE conflicts with SPICE_LLM_BACKEND. Clear SPICE_LLM_DEVICE to select this backend.' >&2
    exit 3
  fi
  if [[ -z "$SPICE_TASK_DEVICE" ]]; then
    for SPICE_TASK_PATTERN in "${SPICE_TASK_PATTERNS[@]}"; do
      SPICE_TASK_DEVICE="$(printf '%s\n' "$SPICE_TASK_DEVICES" | sed -nE "s/^[[:space:]]*($SPICE_TASK_PATTERN):[[:space:]].*/\\1/p" | sed -n '1p')"
      [[ -z "$SPICE_TASK_DEVICE" ]] || break
    done
  fi
  [[ -n "$SPICE_TASK_DEVICE" ]] || {
    if [[ "$SPICE_TASK_BACKEND" == opencl ]]; then
      echo 'No OpenCL device reported. Install llama-cpp-backend-opencl and opencl-vendor-driver, or use the Snapdragon artifact.' >&2
    else
      printf 'No %s GPU/NPU device reported. Check the backend and driver.\n' "$SPICE_TASK_BACKEND" >&2
    fi
    echo 'Recover with SPICE_LLM_BACKEND=cpu bash scripts/start-local-llm.sh.' >&2
    exit 3
  }
fi
SPICE_TASK_ARGS=(--model "$SPICE_TASK_MODEL" --alias "${MOA_MODEL:-spice-local}"
  --host 127.0.0.1 --port "${SPICE_LLM_PORT:-8083}" --ctx-size "${SPICE_LLM_CONTEXT:-4096}"
  --parallel 1 --threads "${SPICE_LLM_THREADS:-4}" --batch-size 128
  --ubatch-size 64 --n-gpu-layers "$SPICE_TASK_LAYERS")
SPICE_TASK_ARGS+=(--device "$SPICE_TASK_DEVICE")
if [[ "$SPICE_TASK_BACKEND" == cpu ]]; then
  SPICE_TASK_ARGS+=(--no-kv-offload --no-op-offload)
  echo 'CPU execution selected; GPU/NPU offload is disabled.'
else
  printf 'Offload device: %s (requested layers: %s). Confirm actual offload in the server log.\n' "$SPICE_TASK_DEVICE" "$SPICE_TASK_LAYERS"
  if [[ "$SPICE_TASK_DEVICE" == Vulkan* ]]; then
    echo 'If Qualcomm Vulkan fails at mul_mat_vec_q4_k, select SPICE_LLM_BACKEND=opencl or cpu; see docs/s24-local-runtime.md.' >&2
  fi
fi
echo 'Starting local model; keep this Termux session or supervise it with your service manager.'
exec "$SPICE_TASK_BIN" "${SPICE_TASK_ARGS[@]}"
