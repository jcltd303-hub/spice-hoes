#!/usr/bin/env bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
PERSONA="${1:-celeste_vale}"
MODE="${2:-}"
case "$PERSONA" in
  celeste_vale|lila_hart|ruby_wren|tess_wilder|zara_voss) ;;
  *) echo "Unknown persona: $PERSONA" >&2; exit 2 ;;
esac
if [[ -n "$MODE" && "$MODE" != --dry-run ]]; then
  echo "Usage: bash scripts/test-local-dream-image.sh [persona] [--dry-run]" >&2
  exit 2
fi

# An explicitly forwarded endpoint/token wins over the device's env files.
DREAM_URL_OVERRIDE="${LOCAL_DREAM_URL:-}"
DREAM_TOKEN_OVERRIDE="${LOCAL_DREAM_TOKEN:-}"
for env_file in "$ROOT/.env" "$ROOT/.env.spicemedia"; do
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done
[[ -z "$DREAM_URL_OVERRIDE" ]] || export LOCAL_DREAM_URL="$DREAM_URL_OVERRIDE"
[[ -z "$DREAM_TOKEN_OVERRIDE" ]] || export LOCAL_DREAM_TOKEN="$DREAM_TOKEN_OVERRIDE"

command -v jq >/dev/null || { echo "jq is required: pkg install jq" >&2; exit 2; }
REFERENCE_ROOT="${SPICE_REFERENCE_ROOT:-$ROOT/data/references}"
mapfile -t CANON < <(find "$REFERENCE_ROOT/$PERSONA" -maxdepth 1 -type f \( \
  -iname 'canon.png' -o -iname 'canon.jpg' -o -iname 'canon.jpeg' -o \
  -iname 'canon-*.png' -o -iname 'canon-*.jpg' -o -iname 'canon-*.jpeg' -o \
  -iname 'canon_*.png' -o -iname 'canon_*.jpg' -o -iname 'canon_*.jpeg' \
\) -print 2>/dev/null | sort)
if (( ${#CANON[@]} == 0 )); then
  echo "No canon images found for $PERSONA under $REFERENCE_ROOT" >&2
  exit 2
fi

SEED="${SPICE_TEST_SEED:-41000}"
STEPS="${SPICE_TEST_STEPS:-24}"
GUIDANCE="${SPICE_TEST_GUIDANCE:-5.5}"
OUT_ROOT="${SPICE_TEST_OUT_ROOT:-$ROOT/data/runs/local-dream-realism}"
RUN_DIR="$OUT_ROOT/$PERSONA/$(date -u +%Y%m%dT%H%M%S)-$SEED-$$"
REQUEST="$(jq -n \
  --arg persona "$PERSONA" --arg root "$REFERENCE_ROOT" --arg out "$RUN_DIR" \
  --arg bank "$ROOT/personas/$PERSONA.safetensors" \
  --arg scene "${SPICE_TEST_SCENE:-plain gray background, direct eye contact}" \
  --argjson seed "$SEED" --argjson steps "$STEPS" --argjson guidance "$GUIDANCE" \
  --argjson width "${SPICE_TEST_WIDTH:-768}" --argjson height "${SPICE_TEST_HEIGHT:-1024}" \
  '{persona_id:$persona, generator:"local-dream", style:"photo-test",
    theme:"photographic realism test", scene:$scene,
    seed:$seed, steps:$steps, guidance:$guidance, width:$width, height:$height,
    best_of_n:1, save_all_attempts:true, stop_on_accept:true,
    reference_root:$root, output_dir:$out, persona_bank:$bank, require_persona_bank:true,
    negative_prompt:"cartoon, anime, illustration, digital painting, comic, 3d render, plastic skin, waxy skin, doll, child, teen, underage, deformed face, blurry, watermark, text"}')"
if [[ "$MODE" == --dry-run ]]; then
  printf '%s\n' "$REQUEST"
  exit 0
fi

BASE="${LOCAL_DREAM_URL:-http://127.0.0.1:8081}"
export LOCAL_DREAM_URL="${BASE%/}"
AUTH=()
[[ -z "${LOCAL_DREAM_TOKEN:-}" ]] || AUTH=(-H "Authorization: Bearer $LOCAL_DREAM_TOKEN")
if ! HEALTH="$(curl --fail --silent --show-error --max-time 5 "${AUTH[@]}" "$LOCAL_DREAM_URL/health")"; then
  echo "Local Dream is not reachable at $LOCAL_DREAM_URL. Start its generation service on the phone or set a reachable LOCAL_DREAM_URL." >&2
  exit 1
fi
printf 'Local Dream health: %s\n' "$HEALTH"
command -v go >/dev/null || { echo "Go is required: pkg install golang" >&2; exit 2; }
command -v python3 >/dev/null || { echo "Python/Pillow is required: python3 -m pip install -r requirements.txt" >&2; exit 2; }
export SPICE_FACE_DETECT_MODEL="${SPICE_FACE_DETECT_MODEL:-$ROOT/models/face/scrfd_10g.bin}"
export SPICE_FACE_EMBED_MODEL="${SPICE_FACE_EMBED_MODEL:-$ROOT/models/face/arcface_w600k_r50.bin}"

mkdir -p "$RUN_DIR"
printf '%s\n' "$REQUEST" > "$RUN_DIR/request.json"
printf '%s\n' "$HEALTH" > "$RUN_DIR/health.json"
# Local Dream handles diffusion; keep the separate QNN core face-only.
unset SPICE_QNN_MODEL_DIR
# Refresh all five prototypes so an old anchor bank cannot override canon scores.
SPICE_CANON_SKIP_CALIBRATION=1 bash "$ROOT/scripts/rebuild-all-persona-banks.sh" > "$RUN_DIR/banks.log"
printf '%s\n' "$REQUEST" | "$ROOT/bin/spicemedia" identity-generate --persona "$PERSONA" > "$RUN_DIR/result.json"
ASSET="$(jq -er '.asset_path' "$RUN_DIR/result.json")"
python3 - "$ASSET" "$RUN_DIR/result.json" <<'VERIFY'
import json, sys
from PIL import Image
with Image.open(sys.argv[1]) as img:
    if img.format != "PNG":
        raise SystemExit("Generated asset is not a PNG")
    size = img.size
    img.verify()
result = json.load(open(sys.argv[2]))
print(f"VALID PNG: {sys.argv[1]} ({size[0]}x{size[1]})")
print(f"STATUS: {result['status']} | identity pass: {result['identity']['passed']} | quality pass: {result['quality_passed']}")
print("Candidate only; canon is preserved. Inspect realism and likeness before promotion.")
VERIFY

DISPLAY="$ASSET"
if [[ -d "$HOME/storage/downloads" && -w "$HOME/storage/downloads" ]]; then
  TARGET="$HOME/storage/downloads/spice-$PERSONA-$(basename "$RUN_DIR").png"
  if cp "$ASSET" "$TARGET"; then DISPLAY="$TARGET"; fi
fi
printf 'SAVED: %s\nRESULT: %s\n' "$DISPLAY" "$RUN_DIR/result.json"
if [[ "${SPICE_TEST_OPEN:-1}" != 0 ]] && command -v termux-open >/dev/null; then
  termux-open --view --content-type image/png "$DISPLAY" || \
    echo "Android viewer could not open the saved PNG; the image remains at $DISPLAY" >&2
fi
