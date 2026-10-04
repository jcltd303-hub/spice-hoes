#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REMOTE="${RCLONE_REMOTE:-gdrive:spice-hoes/mobile-sdcpp}"
DEST="${SPICE_SDCPP_ROOT:-$HOME/spice-models/sdcpp}"
MODEL_NAME="${SPICE_SDCPP_MODEL_NAME:-sdxl-base-q5_1.gguf}"

mkdir -p "$DEST/model" "$DEST/loras" runtime/bin runtime/lib

echo "==> pulling quantized SDXL model + five LoRAs from Drive"
rclone copy "$REMOTE/model" "$DEST/model" -P
rclone copy "$REMOTE/loras" "$DEST/loras" -P

MODEL="$DEST/model/$MODEL_NAME"
[[ -s "$MODEL" ]] || { echo "Missing $MODEL" >&2; exit 2; }

if [[ ! -x runtime/bin/sd-cli ]]; then
  cat >&2 <<'EOF'
runtime/bin/sd-cli is not installed yet.
Download the latest GitHub Actions artifact named:
  spice-sdcpp-android-arm64
and copy runtime/bin + runtime/lib into this repo.
EOF
  exit 3
fi

ENV_FILE="$ROOT/.env.spicemedia"
touch "$ENV_FILE"

set_env() {
  local key="$1" value="$2"
  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i "s#^$key=.*#$key=$value#" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env SPICE_SDCPP_BIN "$ROOT/runtime/bin/sd-cli"
set_env SPICE_SDCPP_MODEL "$MODEL"
set_env SPICE_LORA_DIR "$DEST/loras"
set_env SPICE_IDENTITY_GENERATOR "sdcpp"
set_env SPICE_SDCPP_THREADS "4"
set_env SPICE_SDCPP_FLASH_ATTN "1"

echo
echo "Installed:"
ls -lh "$MODEL"
ls -lh "$DEST/loras"/*.safetensors

echo
echo "Updated $ENV_FILE"
echo "Reload:"
echo "  set -a; source .env.spicemedia; set +a"
echo
echo "Probe devices:"
echo "  $SPICE_SDCPP_BIN --list-devices"
