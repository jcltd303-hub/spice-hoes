#!/usr/bin/env bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$HOME/spice-hoes}"
cd "$ROOT"

# Load the native media/QNN environment used by the working spicemedia setup.
# Prefer the Termux-specific file when present, then fall back to .env.
if [[ -f "$ROOT/.env.spicemedia" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.spicemedia"
  set +a
elif [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Self-heal the two face-model paths when the files are installed in the
# repository-standard Termux location but the env file did not export them.
if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" && -s "$ROOT/models/face/scrfd_10g.bin" ]]; then
  export SPICE_FACE_DETECT_MODEL="$ROOT/models/face/scrfd_10g.bin"
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" && -s "$ROOT/models/face/arcface_w600k_r50.bin" ]]; then
  export SPICE_FACE_EMBED_MODEL="$ROOT/models/face/arcface_w600k_r50.bin"
fi

if [[ -z "${SPICE_FACE_DETECT_MODEL:-}" || ! -s "${SPICE_FACE_DETECT_MODEL:-}" ]]; then
  echo "SCRFD model is not configured/found." >&2
  echo "Expected: $ROOT/models/face/scrfd_10g.bin" >&2
  echo "Run: bash scripts/install-face-embedding-termux.sh" >&2
  exit 4
fi
if [[ -z "${SPICE_FACE_EMBED_MODEL:-}" || ! -s "${SPICE_FACE_EMBED_MODEL:-}" ]]; then
  echo "ArcFace model is not configured/found." >&2
  echo "Expected: $ROOT/models/face/arcface_w600k_r50.bin" >&2
  echo "Run: bash scripts/install-face-embedding-termux.sh" >&2
  exit 5
fi

echo "==> face detector: $SPICE_FACE_DETECT_MODEL"
echo "==> face embedder: $SPICE_FACE_EMBED_MODEL"

REFERENCE_ROOT="${SPICE_REFERENCE_ROOT:-data/references}"
OUT_ROOT="${SPICE_CANON_OUT_ROOT:-data/runs/canon-scenes}"
mkdir -p "$OUT_ROOT" personas

# Self-heal Go module checksums before compiling spicemedia. This is required
# on fresh Termux clones when go.mod contains a dependency that is not yet in go.sum.
echo "==> syncing Go module checksums"
go mod tidy

PERSONAS=(
  zara_voss
  ruby_wren
  tess_wilder
  celeste_vale
  lila_hart
)

echo "==> rebuilding Canon persona safetensors"
for persona in "${PERSONAS[@]}"; do
  ref_dir="$REFERENCE_ROOT/$persona"
  if [[ ! -d "$ref_dir" ]]; then
    echo "missing Canon reference directory: $ref_dir" >&2
    exit 2
  fi

  go run ./cmd/spicemedia persona-bank-build     --persona "$persona"     --reference-root "$REFERENCE_ROOT"     --out "personas/${persona}.safetensors"
done

generate_scene() {
  local persona="$1"
  local theme="$2"
  local scene="$3"
  local out_json="$OUT_ROOT/${persona}.json"

  echo "==> generating $persona"

  # identity-generate scores identity/quality but does not use those scores as
  # an output gate. The generated asset + metadata are emitted regardless of
  # pass/fail score. --require-persona-bank guarantees the freshly rebuilt
  # Canon safetensors is actually used.
  printf '%s' '{}' | go run ./cmd/spicemedia identity-generate     --persona "$persona"     --persona-bank "personas/${persona}.safetensors"     --require-persona-bank     --theme "$theme"     --scene "$scene"     > "$out_json"

  cat "$out_json"
  printf '\n'
}

generate_scene   zara_voss   "editorial portrait in motion"   "humid neon night market, impromptu percussion set, colorful stalls and warm string lights, candid controlled posture, cinematic documentary realism"

generate_scene   ruby_wren   "creative editorial portrait"   "rooftop at dusk with telescope, astronomy notes and self-published zines, city lights softly blurred behind her, modern editorial realism"

generate_scene   tess_wilder   "athletic documentary portrait"   "indoor climbing gym between attempts, chalked hands, route wall behind her, functional training gear, preserve the left below-knee athletic prosthesis when visible"

generate_scene   celeste_vale   "luxury editorial portrait"   "refined boutique hotel interior at golden hour, reviewing material samples and design plans, sculptural jewelry, composed natural realism"

generate_scene   lila_hart   "warm lifestyle portrait"   "ceramics studio in soft daylight, shaping a clay bowl at the wheel, handmade pastel ceramics and herbs nearby, grounded adult contemporary realism"

echo "==> complete"
echo "scene metadata: $OUT_ROOT"
