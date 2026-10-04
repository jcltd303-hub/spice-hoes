#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$HOME/spice-hoes}"
cd "$ROOT"

if [[ -f "$ROOT/.env.spicemedia" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.spicemedia"
  set +a
fi

ANCHOR_ROOT="${SPICE_ANCHOR_ROOT:-$ROOT/assets/persona-anchors}"
REF_ROOT="$ROOT/data/references"
CAL_OUT="${1:-calibration-final-anchors.json}"

PERSONAS=(
  zara_voss
  tess_wilder
  lila_hart
  ruby_wren
  celeste_vale
)

ANCHOR_PERSONAS=(
  zara_voss
  tess_wilder
  lila_hart
  ruby_wren
)

mkdir -p "$ROOT/bin" "$REF_ROOT"

echo "Installing canonical anchors from: $ANCHOR_ROOT"
for persona in "${ANCHOR_PERSONAS[@]}"; do
  src=""
  for candidate in     "$ANCHOR_ROOT/$persona/anchor-01.jpg"     "$ANCHOR_ROOT/$persona/anchor-01.jpeg"     "$ANCHOR_ROOT/$persona/anchor-01.png"     "$ANCHOR_ROOT/$persona.jpg"     "$ANCHOR_ROOT/$persona.jpeg"     "$ANCHOR_ROOT/$persona.png"; do
    if [[ -s "$candidate" ]]; then
      src="$candidate"
      break
    fi
  done

  [[ -n "$src" ]] || {
    echo "Missing anchor for $persona under $ANCHOR_ROOT" >&2
    exit 2
  }

  ext="${src##*.}"
  ext="${ext,,}"
  dst_dir="$REF_ROOT/$persona"
  mkdir -p "$dst_dir"

  rm -f "$dst_dir/anchor-01.jpg" "$dst_dir/anchor-01.jpeg" "$dst_dir/anchor-01.png"
  dst="$dst_dir/anchor-01.$ext"
  cp -f "$src" "$dst"

  echo "  $persona <- $src"
  echo "    sha256=$(sha256sum "$dst" | awk '{print $1}')"
done

echo "Building spicemedia..."
go build -trimpath -o "$ROOT/bin/spicemedia" ./cmd/spicemedia

echo "Rebuilding all five persona safetensor banks..."
for persona in "${PERSONAS[@]}"; do
  ref_dir="$REF_ROOT/$persona"
  [[ -d "$ref_dir" ]] || { echo "Missing reference directory: $ref_dir" >&2; exit 3; }

  count="$(find "$ref_dir" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) | wc -l | tr -d ' ')"
  [[ "$count" -gt 0 ]] || { echo "No usable references for $persona" >&2; exit 4; }

  echo
  echo "=== $persona ($count refs on disk) ==="
  "$ROOT/bin/spicemedia" persona-bank-build     --persona "$persona"     --reference-root "$REF_ROOT"     --out "$ROOT/personas/$persona.safetensors"
done

echo
echo "Recalibrating identity gates..."
go run ./cmd/spicecalibrate   -root "$REF_ROOT"   -out "$CAL_OUT"

echo
echo "=== separability ==="
if command -v jq >/dev/null 2>&1; then
  jq -r '
    .personas[]
    | select(.recommended_max_gate != null)
    | [
        .persona_id,
        ("max=" + (.recommended_max_gate.value|tostring)),
        ("mean=" + (.recommended_mean_gate.value|tostring)),
        ("max_sep=" + (.recommended_max_gate.separable|tostring)),
        ("mean_sep=" + (.recommended_mean_gate.separable|tostring))
      ]
    | @tsv
  ' "$CAL_OUT"
else
  echo "jq not installed; full report: $CAL_OUT"
fi

echo
echo "Banks regenerated:"
for persona in "${PERSONAS[@]}"; do
  ls -lh "$ROOT/personas/$persona.safetensors"
done
echo "Calibration: $CAL_OUT"
