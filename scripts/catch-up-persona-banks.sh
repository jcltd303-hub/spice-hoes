#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "${SPICE_ROOT:-$HOME/spice-hoes}"

if [ -f .env.spicemedia ]; then
  set -a
  . ./.env.spicemedia
  set +a
fi

export SPICE_SCRFD_THRESHOLD="${SPICE_SCRFD_THRESHOLD:-0.12}"

personas=(
  lila_hart
  ruby_wren
  tess_wilder
  zara_voss
)

for persona in "${personas[@]}"; do
  refdir="data/references/$persona"
  bank="personas/$persona.safetensors"
  out="data/identity-catchup/$persona.json"

  echo
  echo "=== $persona ==="

  if [ ! -d "$refdir" ]; then
    echo "SKIP: missing $refdir"
    continue
  fi

  count=$(find "$refdir" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
    ! -iname 'master_*' ! -iname 'contact_*' ! -iname '*_rear*' | wc -l | tr -d ' ')
  if [ "$count" -lt 1 ]; then
    echo "SKIP: no usable references in $refdir"
    continue
  fi

  echo "references=$count"
  ./bin/spicemedia persona-bank-build \
    --persona "$persona" \
    --reference-root data/references \
    --out "$bank"

  mkdir -p "$(dirname "$out")"

  cat <<JSON | ./bin/spicemedia identity-generate \
    --persona-bank "$bank" \
    --require-persona-bank | tee "$out"
{
  "persona_id": "$persona",
  "theme": "identity reference portrait",
  "scene": "clean natural-light portrait, looking directly at camera, realistic skin, neutral expression",
  "style": "photorealistic",
  "seed": 48,
  "width": 1024,
  "height": 1024,
  "steps": 20,
  "guidance": 6.5,
  "generator": "local-dream",
  "best_of_n": 4,
  "swap_top_k": 2,
  "stop_on_accept": true
}
JSON

done
