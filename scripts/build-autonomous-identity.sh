#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$(pwd)}"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PERSONA_ID="${1:-}"
GENERATOR="${2:-${SPICE_IDENTITY_GENERATOR:-local-dream}}"
SWAP_MODE="${3:-auto}"
SEED="${4:-41000}"
RUN_ID="${5:-${SPICE_AUTONOMOUS_RUN_ID:-}}"

if [[ -z "$PERSONA_ID" ]]; then
  echo "usage: $0 <persona_id> [local-dream|qnn] [auto|required|disabled] [seed] [run_id]" >&2
  exit 2
fi

if [[ "$GENERATOR" == "local-dream" ]]; then
  : "${LOCAL_DREAM_URL:=http://127.0.0.1:8081}"
  export LOCAL_DREAM_URL
fi

if [[ "$SWAP_MODE" != "disabled" ]]; then
  INSWAPPER_PATH="${SPICE_INSWAPPER_MODEL:-$ROOT/models/face/inswapper_128.onnx}"
  ORT_PATH="${SPICE_ONNXRUNTIME_LIB:-$ROOT/runtime/lib/libonnxruntime.so}"
  if [[ ! -s "$INSWAPPER_PATH" || ! -s "$ORT_PATH" ]]; then
    echo "InSwapper runtime assets missing; installing..."
    bash "$ROOT/scripts/install-inswapper-termux.sh"
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi
fi

if [[ ! -x "$ROOT/bin/spicemedia" ]] || [[ "$ROOT/cmd/spicemedia/main.go" -nt "$ROOT/bin/spicemedia" ]]; then
  echo "Building Go-only spicemedia..."
  go mod tidy
  mkdir -p "$ROOT/bin"
  go build -trimpath -o "$ROOT/bin/spicemedia" ./cmd/spicemedia
fi

cat <<JSON | "$ROOT/bin/spicemedia" identity-autonomous
{
  "persona_id": "$PERSONA_ID",
  "run_id": "$RUN_ID",
  "generator": "$GENERATOR",
  "swap_mode": "$SWAP_MODE",
  "seed": $SEED,
  "max_attempts": ${SPICE_IDENTITY_MAX_ATTEMPTS:-48},
  "pose_attempts": ${SPICE_POSE_MAX_ATTEMPTS:-4},
  "identity_threshold": ${SPICE_IDENTITY_THRESHOLD:-0.82},
  "quality_threshold": ${SPICE_QUALITY_THRESHOLD:-0.78}
}
JSON

echo
if command -v find >/dev/null 2>&1; then
  DOC_ROOT="${SPICE_DOCUMENTS_ROOT:-$HOME/storage/documents}"
  echo "Latest mirrored autonomous outputs:"
  find "$DOC_ROOT/sh/$PERSONA_ID/autonomous" -maxdepth 2 -type f \( -name 'identity_master_9pose.png' -o -name 'identity_portfolio_manifest.json' \) -print 2>/dev/null | sort | tail -n 4 || true
fi
