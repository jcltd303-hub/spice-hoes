#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${1:-$HOME/spice-models}"
MODEL_NAME="${SPICE_QNN_MODEL_NAME:-intorealism_ultra_v11}"
ZIP_NAME="${SPICE_QNN_MODEL_ZIP:-intorealism_ultra_v11_qnn2.28_8gen3.zip}"
HF_REPO="${SPICE_QNN_HF_REPO:-xororz/sdxl-qnn}"
HF_REV="${SPICE_QNN_HF_REV:-7b72d4b5c7dcbbb674798c2640aac6697b5f0c33}"
URL="https://huggingface.co/${HF_REPO}/resolve/${HF_REV}/${ZIP_NAME}"
ZIP_PATH="$DEST_ROOT/$ZIP_NAME"
MODEL_DIR="$DEST_ROOT/$MODEL_NAME"

command -v curl >/dev/null || { echo "curl is required: pkg install curl" >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip is required: pkg install unzip" >&2; exit 1; }

mkdir -p "$DEST_ROOT"

HEADERS=()
if [[ -n "${HF_TOKEN:-}" ]]; then
  HEADERS=(-H "Authorization: Bearer $HF_TOKEN")
fi

echo "Downloading prebuilt SDXL/QNN model:"
echo "  $HF_REPO/$ZIP_NAME"
echo "Destination:"
echo "  $ZIP_PATH"

curl --fail --location --retry 8 --retry-delay 5 --continue-at - --progress-bar \
  "${HEADERS[@]}" "$URL" --output "$ZIP_PATH"

SIZE="$(wc -c < "$ZIP_PATH")"
if (( SIZE < 3000000000 )); then
  echo "Downloaded archive is unexpectedly small: $SIZE bytes" >&2
  exit 2
fi

rm -rf "$MODEL_DIR"
mkdir -p "$MODEL_DIR"
unzip -q "$ZIP_PATH" -d "$MODEL_DIR"

# Flatten a single top-level directory if the archive includes one.
shopt -s nullglob dotglob
entries=("$MODEL_DIR"/*)
if (( ${#entries[@]} == 1 )) && [[ -d "${entries[0]}" ]]; then
  tmp="$MODEL_DIR.__tmp"
  rm -rf "$tmp"
  mv "${entries[0]}" "$tmp"
  rmdir "$MODEL_DIR"
  mv "$tmp" "$MODEL_DIR"
fi
shopt -u nullglob dotglob

# Accept the actual Local Dream SDXL/QNN pack as-is. Verify the critical runtime pieces.
UNET="$(find "$MODEL_DIR" -type f -name 'unet.bin' -print -quit)"
VAE="$(find "$MODEL_DIR" -type f -name 'vae_decoder.bin' -print -quit)"
TOKENIZER="$(find "$MODEL_DIR" -type f -name 'tokenizer.json' -print -quit)"
if [[ -z "$UNET" || -z "$VAE" || -z "$TOKENIZER" ]]; then
  echo "Archive does not look like a Local Dream/QNN SDXL model pack." >&2
  find "$MODEL_DIR" -maxdepth 2 -type f | head -80 >&2
  exit 3
fi

# If the payload was nested deeper, point the runtime at the common directory containing unet.bin.
MODEL_DIR="$(dirname "$UNET")"

ENV_FILE="$ROOT/.env.spicemedia"
touch "$ENV_FILE"

if grep -q '^SPICE_QNN_MODEL_DIR=' "$ENV_FILE"; then
  sed -i "s#^SPICE_QNN_MODEL_DIR=.*#SPICE_QNN_MODEL_DIR=$MODEL_DIR#" "$ENV_FILE"
else
  printf '\nSPICE_QNN_MODEL_DIR=%s\n' "$MODEL_DIR" >> "$ENV_FILE"
fi

if grep -q '^SPICE_QNN_TYPE=' "$ENV_FILE"; then
  sed -i 's#^SPICE_QNN_TYPE=.*#SPICE_QNN_TYPE=sdxl#' "$ENV_FILE"
else
  printf 'SPICE_QNN_TYPE=sdxl\n' >> "$ENV_FILE"
fi

printf '%s\n' "$HF_REPO" > "$MODEL_DIR/SOURCE_HF_REPO"
printf '%s\n' "$HF_REV" > "$MODEL_DIR/SOURCE_HF_REV"
printf '%s\n' "$ZIP_NAME" > "$MODEL_DIR/SOURCE_HF_FILE"

if [[ ! -x "$ROOT/bin/spicemedia" ]]; then
  echo
  echo "spicemedia binary missing; building Go media tools..."
  command -v go >/dev/null || { echo "Go is required: pkg install golang" >&2; exit 4; }
  bash "$ROOT/scripts/build-go-tools.sh"
fi

echo
echo "Installed prebuilt QNN model:"
echo "  $MODEL_DIR"
echo
echo "Updated $ENV_FILE:"
echo "  SPICE_QNN_TYPE=sdxl"
echo "  SPICE_QNN_MODEL_DIR=$MODEL_DIR"
echo
echo "Reload and verify:"
echo "  set -a; source .env.spicemedia; set +a"
echo "  echo '{}' | ./bin/spicemedia health"
