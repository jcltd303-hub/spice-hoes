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

BIN="${SPICE_MEDIA_BIN:-$ROOT/bin/spicemedia}"
if [[ ! -x "$BIN" ]]; then
  echo "Building spicemedia..."
  mkdir -p "$ROOT/bin"
  go build -trimpath -o "$BIN" ./cmd/spicemedia
fi

THEME="${1:-identity portrait}"
SCENE="${2:-clean editorial portrait, face unobscured, natural expression, realistic lighting}"

PERSONAS=(
  zara_voss
  tess_wilder
  lila_hart
  ruby_wren
  celeste_vale
)

for persona in "${PERSONAS[@]}"; do
  yaml="$ROOT/personas/$persona.yaml"
  bank="$ROOT/personas/$persona.safetensors"

  [[ -s "$yaml" ]] || { echo "Missing persona YAML: $yaml" >&2; exit 2; }
  [[ -s "$bank" ]] || { echo "Missing persona bank: $bank" >&2; exit 3; }

  echo
  echo "=== $persona ==="
  "$BIN" identity-generate     --persona "$persona"     --theme "$THEME"     --scene "$SCENE"     --persona-bank "$bank"     --require-persona-bank     < /dev/null
done
