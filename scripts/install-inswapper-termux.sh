#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="${SPICE_HOES_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

command -v curl >/dev/null || { echo "curl required: pkg install curl" >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip required: pkg install unzip" >&2; exit 1; }

ENV_FILE="$ROOT/.env"
SPICEMEDIA_ENV_FILE="$ROOT/.env.spicemedia"
[[ -f "$ENV_FILE" ]] || cp "$ROOT/.env.example" "$ENV_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

MODEL_DIR="$ROOT/models/face"
RUNTIME_DIR="$ROOT/runtime/lib"
mkdir -p "$MODEL_DIR" "$RUNTIME_DIR"

INSWAPPER_URL="${SPICE_INSWAPPER_MODEL_URL:-https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx}"
INSWAPPER_PATH="${SPICE_INSWAPPER_MODEL:-$MODEL_DIR/inswapper_128.onnx}"
ORT_PATH="${SPICE_ONNXRUNTIME_LIB:-$RUNTIME_DIR/libonnxruntime.so}"

echo "[1/4] Installing InsightFace InSwapper model"
if [[ ! -s "$INSWAPPER_PATH" ]]; then
  tmp_model="$INSWAPPER_PATH.part"
  rm -f "$tmp_model"
  curl -fL --retry 3 --retry-delay 2 "$INSWAPPER_URL" -o "$tmp_model"
  test -s "$tmp_model"
  mv "$tmp_model" "$INSWAPPER_PATH"
fi

echo "[2/4] Resolving latest ONNX Runtime Android release"
if [[ ! -s "$ORT_PATH" ]]; then
  META_URL="https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/maven-metadata.xml"
  ORT_VERSION="${SPICE_ONNXRUNTIME_VERSION:-}"
  if [[ -z "$ORT_VERSION" ]]; then
    ORT_VERSION="$(curl -fsSL "$META_URL" | sed -n 's:.*<release>\(.*\)</release>.*:\1:p' | head -n1)"
  fi
  if [[ -z "$ORT_VERSION" ]]; then
    echo "Could not resolve ONNX Runtime version." >&2
    exit 1
  fi
  AAR_URL="https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/$ORT_VERSION/onnxruntime-android-$ORT_VERSION.aar"
  TMP_DIR="$ROOT/.onnxruntime-android"
  rm -rf "$TMP_DIR"
  mkdir -p "$TMP_DIR"
  echo "Using ONNX Runtime $ORT_VERSION"
  curl -fL --retry 3 --retry-delay 2 "$AAR_URL" -o "$TMP_DIR/onnxruntime.aar"
  unzip -q "$TMP_DIR/onnxruntime.aar" "jni/arm64-v8a/libonnxruntime.so" -d "$TMP_DIR"
  install -m 0755 "$TMP_DIR/jni/arm64-v8a/libonnxruntime.so" "$ORT_PATH"
  rm -rf "$TMP_DIR"
fi

echo "[3/4] Verifying runtime assets"
test -s "$INSWAPPER_PATH" || { echo "Missing model: $INSWAPPER_PATH" >&2; exit 1; }
test -s "$ORT_PATH" || { echo "Missing runtime: $ORT_PATH" >&2; exit 1; }

upsert_env_file() {
  local file="$1"
  local key="$2"
  local value="$3"
  [[ -f "$file" ]] || touch "$file"
  if grep -qE "^${key}=" "$file"; then
    sed -i "s|^${key}=.*$|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

upsert_env() {
  local key="$1"
  local value="$2"
  upsert_env_file "$ENV_FILE" "$key" "$value"
  upsert_env_file "$SPICEMEDIA_ENV_FILE" "$key" "$value"
}

echo "[4/4] Updating .env and .env.spicemedia"
upsert_env SPICE_INSWAPPER_MODEL "$INSWAPPER_PATH"
upsert_env SPICE_ONNXRUNTIME_LIB "$ORT_PATH"
upsert_env SPICE_INSWAPPER_MODEL_URL "$INSWAPPER_URL"

echo
echo "Installed:"
echo "  InSwapper:    $INSWAPPER_PATH"
echo "  ONNX Runtime: $ORT_PATH"
echo
echo "Configured in:"
echo "  $ENV_FILE"
echo "  $SPICEMEDIA_ENV_FILE"
