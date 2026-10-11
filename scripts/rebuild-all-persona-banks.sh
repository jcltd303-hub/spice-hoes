#!/usr/bin/env bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
for env_file in "$ROOT/.env" "$ROOT/.env.spicemedia"; do
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done
REF_ROOT="${SPICE_REFERENCE_ROOT:-$ROOT/data/references}"
CAL_OUT="${1:-$ROOT/data/runs/canon-bank-calibration.json}"
BACKUP_ROOT="$ROOT/data/reference-archive/persona-banks/$(date -u +%Y%m%dT%H%M%S)-$$"
PERSONAS=(zara_voss tess_wilder lila_hart ruby_wren celeste_vale)

# Only canon is authoritative; never reinstall old assets/persona-anchors.
for persona in "${PERSONAS[@]}"; do
  count="$(find "$REF_ROOT/$persona" -maxdepth 1 -type f \( \
    -iname 'canon.png' -o -iname 'canon.jpg' -o -iname 'canon.jpeg' -o \
    -iname 'canon-*.png' -o -iname 'canon-*.jpg' -o -iname 'canon-*.jpeg' -o \
    -iname 'canon_*.png' -o -iname 'canon_*.jpg' -o -iname 'canon_*.jpeg' \
  \) -print 2>/dev/null | wc -l)"
  (( count > 0 )) || { echo "Missing canon for $persona under $REF_ROOT" >&2; exit 2; }
done
if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" ]]; then
  export SPICE_FACE_DETECT_MODEL="$ROOT/models/face/scrfd_10g.bin"
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" ]]; then
  export SPICE_FACE_EMBED_MODEL="$ROOT/models/face/arcface_w600k_r50.bin"
fi
for model in "$SPICE_FACE_DETECT_MODEL" "$SPICE_FACE_EMBED_MODEL"; do
  [[ -s "$model" ]] || { echo "Missing face model: $model. Run bash scripts/install-face-embedding-termux.sh" >&2; exit 2; }
done
command -v go >/dev/null || { echo "Go is required: pkg install golang" >&2; exit 2; }
unset SPICE_QNN_MODEL_DIR
mkdir -p "$ROOT/bin" "$BACKUP_ROOT" "$(dirname "$CAL_OUT")"
go build -trimpath -o "$ROOT/bin/spicemedia" ./cmd/spicemedia
# Build the complete pack in staging before replacing any existing bank.
for persona in "${PERSONAS[@]}"; do
  "$ROOT/bin/spicemedia" persona-bank-build --persona "$persona" \
    --reference-root "$REF_ROOT" --out "$BACKUP_ROOT/$persona.new.safetensors"
done
for persona in "${PERSONAS[@]}"; do
  bank="$ROOT/personas/$persona.safetensors"
  [[ ! -f "$bank" ]] || cp -p "$bank" "$BACKUP_ROOT/$persona.previous.safetensors"
  mv "$BACKUP_ROOT/$persona.new.safetensors" "$bank"
done
if [[ "${SPICE_CANON_SKIP_CALIBRATION:-0}" != 1 ]]; then
  go run ./cmd/spicecalibrate -root "$REF_ROOT" -out "$CAL_OUT"
fi
printf 'Rebuilt five persona banks from canon only. Previous banks: %s\n' "$BACKUP_ROOT"
