#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${SPICE_ENV_FILE:-$ROOT/.env.spicemedia}"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }

set -a
source "$ENV_FILE"
set +a

CORE="${SPICE_QNN_CORE_BIN:-$ROOT/runtime/bin/spice-qnn-core}"
MODEL_DIR="${SPICE_QNN_MODEL_DIR:-}"
LIB_DIR="${SPICE_QNN_LIB_DIR:-$ROOT/runtime/lib}"
PORT="${SPICE_QNN_PORT:-18081}"
LOG="${SPICE_QNN_LOG:-$ROOT/data/spicemedia/qnn-core.log}"
TYPE="${SPICE_QNN_TYPE:-sdxl}"

[[ -x "$CORE" ]] || { echo "Missing QNN core: $CORE" >&2; exit 1; }
[[ -d "$MODEL_DIR" ]] || { echo "Missing model dir: $MODEL_DIR" >&2; exit 1; }
[[ -d "$LIB_DIR" ]] || { echo "Missing QNN lib dir: $LIB_DIR" >&2; exit 1; }

mkdir -p "$(dirname "$LOG")"

pkill -f 'spice-qnn-core' >/dev/null 2>&1 || true
pkill -f 'stable_diffusion_core' >/dev/null 2>&1 || true

export LD_LIBRARY_PATH="$LIB_DIR:/system/lib64:/vendor/lib64:/vendor/lib64/egl"
export DSP_LIBRARY_PATH="$LIB_DIR;/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/dsp"
export ADSP_LIBRARY_PATH="$DSP_LIBRARY_PATH"

args=(
  --type "$TYPE"
  --model_dir "$MODEL_DIR"
  --lib_dir "$LIB_DIR"
  --port "$PORT"
  --no_img2img
  --lowram
)

if [[ -n "${SPICE_FACE_EMBED_MODEL:-}" && -f "$SPICE_FACE_EMBED_MODEL" ]]; then
  args+=(--identity_vision "$SPICE_FACE_EMBED_MODEL")
fi
if [[ -n "${SPICE_FACE_DETECT_MODEL:-}" && -f "$SPICE_FACE_DETECT_MODEL" ]]; then
  args+=(--face_detector "$SPICE_FACE_DETECT_MODEL")
fi

: > "$LOG"
nohup "$CORE" "${args[@]}" >>"$LOG" 2>&1 &
PID=$!

echo "Started SDXL low-RAM core PID $PID"
echo "Model: $MODEL_DIR"
echo "Log:   $LOG"

for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "QNN core healthy on port $PORT"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "QNN core exited during startup." >&2
    tail -n 120 "$LOG" >&2 || true
    exit 2
  fi
  sleep 1
done

echo "QNN core did not become healthy." >&2
tail -n 120 "$LOG" >&2 || true
exit 3
