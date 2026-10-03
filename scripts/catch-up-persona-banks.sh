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

scenes=(
  "clean natural-light front portrait, looking directly at camera, neutral expression, realistic skin, face unobscured"
  "clean natural-light three-quarter portrait turned slightly left, neutral expression, realistic skin, face unobscured"
  "clean natural-light three-quarter portrait turned slightly right, neutral expression, realistic skin, face unobscured"
  "clean natural-light soft profile portrait, relaxed neutral expression, realistic skin, face unobscured"
)

usable_ref_count() {
  local refdir="$1"
  find "$refdir" -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
    ! -iname 'master_*' ! -iname 'contact_*' ! -iname '*_rear*' | wc -l | tr -d ' '
}

extract_asset_path() {
  python3 - "$1" <<'PY'
import json, sys
text=open(sys.argv[1],errors="ignore").read()
starts=[]
for needle in ('{"ok"', '{"status"', '{"persona_id"'):
    pos=text.rfind(needle)
    if pos >= 0:
        starts.append(pos)
if not starts:
    raise SystemExit(1)
obj=json.loads(text[max(starts):])
print(obj.get("asset_path",""))
PY
}

generate_bootstrap() {
  local persona="$1"
  local scene="$2"
  local seed="$3"
  local target="$4"
  local bank="${5:-}"
  local tmp
  tmp=$(mktemp)

  if [ -n "$bank" ]; then
    cat <<JSON | ./bin/spicemedia identity-generate \
      --persona-bank "$bank" \
      --require-persona-bank | tee "$tmp"
{
  "persona_id": "$persona",
  "theme": "identity reference portrait",
  "scene": "$scene",
  "style": "photorealistic",
  "seed": $seed,
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
  else
    cat <<JSON | ./bin/spicemedia identity-generate | tee "$tmp"
{
  "persona_id": "$persona",
  "theme": "identity reference portrait",
  "scene": "$scene",
  "style": "photorealistic",
  "seed": $seed,
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
  fi

  local asset
  asset=$(extract_asset_path "$tmp")
  rm -f "$tmp"

  if [ -z "$asset" ] || [ ! -s "$asset" ]; then
    echo "ERROR: bootstrap asset missing for $persona -> $target" >&2
    return 1
  fi

  cp -f "$asset" "$target"
  echo "bootstrap -> $target"
}

for persona in "${personas[@]}"; do
  refdir="data/references/$persona"
  bank="personas/$persona.safetensors"
  out="data/identity-catchup/$persona.json"

  echo
  echo "=== $persona ==="
  mkdir -p "$refdir"

  count=$(usable_ref_count "$refdir")
  echo "starting references=$count"

  # With no references at all, create exactly one prompt-only anchor. Every
  # subsequent bootstrap portrait is generated through a safetensors centroid
  # built from the references accumulated so far.
  if [ "$count" -eq 0 ]; then
    generate_bootstrap "$persona" "${scenes[0]}" 48 "$refdir/bootstrap-1.png"
    count=$(usable_ref_count "$refdir")
  fi

  # Build the first identity anchor from the available reference(s).
  if [ "$count" -gt 0 ] && [ "$count" -lt 4 ]; then
    ./bin/spicemedia persona-bank-build \
      --persona "$persona" \
      --reference-root data/references \
      --out "$bank"
  fi

  # Fill the pack to four references. After every new portrait, rebuild the
  # centroid so the next view is conditioned by the progressively stronger
  # identity bank rather than four independent prompt-only faces.
  for i in 1 2 3; do
    count=$(usable_ref_count "$refdir")
    if [ "$count" -ge 4 ]; then
      break
    fi

    idx=$((i+1))
    target="$refdir/bootstrap-$idx.png"
    if [ -s "$target" ]; then
      continue
    fi

    generate_bootstrap "$persona" "${scenes[$i]}" $((48+i)) "$target" "$bank"

    ./bin/spicemedia persona-bank-build \
      --persona "$persona" \
      --reference-root data/references \
      --out "$bank"
  done

  count=$(usable_ref_count "$refdir")
  if [ "$count" -lt 4 ]; then
    echo "ERROR: $persona has only $count usable references after bootstrap" >&2
    exit 1
  fi

  echo "references=$count"

  # Final centroid from the complete reference pack.
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
