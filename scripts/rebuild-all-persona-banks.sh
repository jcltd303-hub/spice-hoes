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

echo
echo "Building anchor-weighted discriminative persona banks..."
go run ./cmd/spicediscrim \
  -root "$REF_ROOT" \
  -bank-dir "$ROOT/personas" \
  -anchor-weight "${SPICE_IDENTITY_ANCHOR_WEIGHT:-0.70}" \
  -out "$ROOT/discriminative-banks.json"

echo
echo "Calibrating discriminative prototype margins..."
go run ./cmd/spicediscrimcheck \
  -root "$REF_ROOT" \
  -bank-dir "$ROOT/personas" \
  -margin "${SPICE_IDENTITY_MARGIN_THRESHOLD:-0.05}" \
  -out "$ROOT/discriminative-calibration.json"

echo
echo "Recalibrating raw reference diagnostics..."
go run ./cmd/spicecalibrate \
  -root "$REF_ROOT" \
  -out "$CAL_OUT"

echo
echo "=== discriminative prototype build ==="
if command -v jq >/dev/null 2>&1; then
  jq -r '
    .personas[]
    | [
        .persona_id,
        ("anchors=" + ((.anchor_labels|length)|tostring)),
        ("support_kept=" + ((.support_kept|length)|tostring)),
        ("support_rejected=" + ((.support_rejected|length)|tostring))
      ]
    | @tsv
  ' "$ROOT/discriminative-banks.json"
else
  echo "jq not installed; report: $ROOT/discriminative-banks.json"
fi

echo
echo "Banks regenerated:"
for persona in "${PERSONAS[@]}"; do
  ls -lh "$ROOT/personas/$persona.safetensors"
done
echo "Calibration: $CAL_OUT"
