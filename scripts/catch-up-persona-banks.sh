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

  mkdir -p "$refdir"

  count=$(find "$refdir" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
    ! -iname 'master_*' ! -iname 'contact_*' ! -iname '*_rear*' | wc -l | tr -d ' ')

  if [ "$count" -lt 4 ]; then
    echo "bootstrapping initial references: have=$count need=4"
    scenes=(
      "clean natural-light front portrait, looking directly at camera, neutral expression, realistic skin, face unobscured"
      "clean natural-light three-quarter portrait turned slightly left, neutral expression, realistic skin, face unobscured"
      "clean natural-light three-quarter portrait turned slightly right, neutral expression, realistic skin, face unobscured"
      "clean natural-light soft profile portrait, relaxed neutral expression, realistic skin, face unobscured"
    )

    for i in 0 1 2 3; do
      idx=$((i+1))
      target="$refdir/bootstrap-$idx.png"
      if [ -s "$target" ]; then
        continue
      fi

      tmp=$(mktemp)
      cat <<JSON | ./bin/spicemedia identity-generate | tee "$tmp"
{
  "persona_id": "$persona",
  "theme": "identity reference portrait",
  "scene": "${scenes[$i]}",
  "style": "photorealistic",
  "seed": $((48+i)),
  "width": 1024,
  "height": 1024,
  "steps": 20,
  "guidance": 6.5,
  "generator": "local-dream",
  "best_of_n": 1,
  "swap_top_k": 1,
  "stop_on_accept": true
}
JSON

      asset=$(python3 - "$tmp" <<'PY'
import json, sys
path=sys.argv[1]
text=open(path,errors="ignore").read()
start=text.rfind('{"ok"')
if start < 0:
    start=text.rfind('{"status"')
if start < 0:
    raise SystemExit(1)
obj=json.loads(text[start:])
print(obj.get("asset_path",""))
PY
)
      rm -f "$tmp"

      if [ -z "$asset" ] || [ ! -s "$asset" ]; then
        echo "ERROR: bootstrap asset missing for $persona ref $idx"
        exit 1
      fi

      cp -f "$asset" "$target"
      echo "bootstrap ref $idx -> $target"
    done

    count=$(find "$refdir" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
      ! -iname 'master_*' ! -iname 'contact_*' ! -iname '*_rear*' | wc -l | tr -d ' ')
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
