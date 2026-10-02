#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

DEST_ROOT="${1:-$HOME/spice-checkpoints}"
MODEL_REPO="cyberdelia/CyberRealisticXL_Desire"
MODEL_FILE="CyberRealisticXL_Desire_V3_FP16.safetensors"
BASE_URL="https://huggingface.co/${MODEL_REPO}/resolve/main/${MODEL_FILE}?download=true"
DEST="$DEST_ROOT/$MODEL_FILE"

command -v curl >/dev/null || { echo "curl is required: pkg install curl" >&2; exit 1; }

mkdir -p "$DEST_ROOT"

HEADERS=()
if [[ -n "${HF_TOKEN:-}" ]]; then
  HEADERS=(-H "Authorization: Bearer $HF_TOKEN")
fi

echo "Downloading:"
echo "  $MODEL_REPO"
echo "  $MODEL_FILE"
echo
echo "Destination:"
echo "  $DEST"
echo
echo "This is a ~6.94 GB FP16 SDXL checkpoint. Download is resumable."

curl \
  --fail \
  --location \
  --retry 8 \
  --retry-delay 5 \
  --continue-at - \
  --progress-bar \
  "${HEADERS[@]}" \
  "$BASE_URL" \
  --output "$DEST"

SIZE="$(wc -c < "$DEST")"
if (( SIZE < 6000000000 )); then
  echo "Downloaded file is unexpectedly small: $SIZE bytes" >&2
  exit 2
fi

printf '%s\n' "$MODEL_REPO" > "$DEST.repo"
printf '%s\n' "$MODEL_FILE" > "$DEST.filename"

echo
echo "Downloaded successfully:"
ls -lh "$DEST"
echo
echo "NOTE: spice-qnn-core cannot load SafeTensors directly."
echo "This checkpoint still needs conversion to the Spice/Local-Dream SDXL QNN layout before generation."
