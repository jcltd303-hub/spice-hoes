#!/usr/bin/env bash
set -euo pipefail

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
