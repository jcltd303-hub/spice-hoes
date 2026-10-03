#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$HOME/spice-hoes}"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

BASE="${LOCAL_DREAM_URL:-http://127.0.0.1:8081}"
OUT_DIR="$HOME/storage/downloads"
mkdir -p "$OUT_DIR" "$ROOT/data"

RESP="$ROOT/data/local-dream-last-response.txt"
RAW="$ROOT/data/local-dream-last.raw"
OUT="$OUT_DIR/spice-test-$(date +%s).png"

if ! curl --fail --silent --show-error --max-time 3 "$BASE/health" >/dev/null; then
  echo "Local Dream is not running at $BASE" >&2
  exit 1
fi

HEADERS=(
  -H 'Content-Type: application/json'
  -H 'Accept: text/event-stream'
)
if [[ -n "${LOCAL_DREAM_TOKEN:-}" ]]; then
  HEADERS+=( -H "Authorization: Bearer $LOCAL_DREAM_TOKEN" )
fi

curl --fail --no-buffer --silent --show-error \
  "${HEADERS[@]}" \
  "$BASE/generate" \
  --data-binary @- > "$RESP" <<'JSON'
{
  "prompt": "professional photorealistic studio portrait of a fictional adult woman, age 28, natural facial proportions, realistic eyes, natural skin texture, subtle asymmetry, dark glossy hair, elegant neutral expression, soft diffused light, 85mm portrait photography, clean gray studio background",
  "negative_prompt": "child, teen, underage, cartoon, anime, illustration, 3d render, plastic skin, waxy skin, malformed face, distorted anatomy, duplicate features, blurry, watermark, logo, text",
  "width": 768,
  "height": 1024,
  "seed": 41000
}
JSON

DATA="$(
  awk '
    /^event:[[:space:]]*complete/ { complete=1; next }
    complete && /^data:/ {
      sub(/^data:[[:space:]]*/, "")
      print
      exit
    }
  ' "$RESP"
)"

if [[ -z "$DATA" ]]; then
  echo "No complete event."
  cat "$RESP"
  exit 1
fi

WIDTH="$(printf '%s\n' "$DATA" | jq -r '.width // 0')"
HEIGHT="$(printf '%s\n' "$DATA" | jq -r '.height // 0')"
CHANNELS="$(printf '%s\n' "$DATA" | jq -r '.channels // 0')"

printf '%s\n' "$DATA" \
  | jq -er '.image // .image_base64' \
  | sed 's#^data:image/[^;]*;base64,##' \
  | base64 -d > "$RAW"

MAGIC="$(od -An -tx1 -N8 "$RAW" | tr -d ' \n')"

case "$MAGIC" in
  89504e470d0a1a0a*)
    cp "$RAW" "$OUT"
    ;;
  ffd8ff*)
    OUT="${OUT%.png}.jpg"
    cp "$RAW" "$OUT"
    ;;
  *)
    ACTUAL="$(wc -c < "$RAW" | tr -d ' ')"
    PIXELS=$((WIDTH * HEIGHT))

    if [[ "$CHANNELS" -ne 3 && "$CHANNELS" -ne 4 ]]; then
      if [[ "$ACTUAL" -eq $((PIXELS * 4)) ]]; then
        CHANNELS=4
      elif [[ "$ACTUAL" -eq $((PIXELS * 3)) ]]; then
        CHANNELS=3
      fi
    fi

    EXPECTED=$((WIDTH * HEIGHT * CHANNELS))
    if [[ "$WIDTH" -le 0 || "$HEIGHT" -le 0 || ( "$CHANNELS" -ne 3 && "$CHANNELS" -ne 4 ) || "$ACTUAL" -ne "$EXPECTED" ]]; then
      echo "Unsupported image payload."
      echo "width=$WIDTH height=$HEIGHT channels=$CHANNELS bytes=$ACTUAL expected=$EXPECTED"
      echo "raw response: $RESP"
      exit 1
    fi

    command -v ffmpeg >/dev/null 2>&1 || {
      echo "Raw image received. Install ffmpeg once with:"
      echo "  pkg install ffmpeg"
      exit 1
    }

    PIX_FMT="rgb24"
    [[ "$CHANNELS" -eq 4 ]] && PIX_FMT="rgba"

    ffmpeg -loglevel error -y \
      -f rawvideo \
      -pixel_format "$PIX_FMT" \
      -video_size "${WIDTH}x${HEIGHT}" \
      -i "$RAW" \
      -frames:v 1 "$OUT"
    ;;
esac

if [[ "$OUT" == *.png ]]; then
  OUT_MAGIC="$(od -An -tx1 -N8 "$OUT" | tr -d ' \n')"
  if [[ "$OUT_MAGIC" != 89504e470d0a1a0a* ]]; then
    echo "Invalid PNG signature: $OUT_MAGIC" >&2
    exit 1
  fi
fi

echo
echo "VALID IMAGE:"
file "$OUT"
ls -lh "$OUT"
echo "SAVED: $OUT"
echo "RAW RESPONSE: $RESP"

termux-open "$OUT"
