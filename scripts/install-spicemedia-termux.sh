#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v go >/dev/null || { echo "Go is required: pkg install golang" >&2; exit 1; }
command -v gh >/dev/null || { echo "GitHub CLI is required: pkg install gh" >&2; exit 1; }

echo "[1/5] Building Go media binaries"
mkdir -p bin
go build -trimpath -ldflags="-s -w" -o bin/spiceimg ./cmd/spiceimg
go build -trimpath -ldflags="-s -w" -o bin/spicemedia ./cmd/spicemedia

echo "[2/5] Installing Spice QNN runtime artifact"
bash scripts/install-spice-qnn-runtime-termux.sh

echo "[3/5] Verifying Spice native runtime"
chmod +x runtime/bin/spice-qnn-core bin/spicemedia bin/spiceimg
test -s runtime/bin/spice-qnn-core
test -s runtime/lib/libQnnHtp.so
test -s runtime/lib/libQnnSystem.so

echo "[4/5] Installing face detector/embedding models when available"
FACE_RUN="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Face Embedding QNN" --status success --limit 1 --json databaseId --jq '.[0].databaseId' || true)"
if [[ -n "$FACE_RUN" && "$FACE_RUN" != "null" ]]; then
  bash scripts/install-face-embedding-termux.sh
else
  echo "No successful face-model artifact yet; continuing without it."
fi

echo "[5/5] Updating canonical .env"

ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
fi

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*$|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

upsert_env SPICE_MEDIA_PROVIDER go
upsert_env SPICE_MEDIA_BIN "$ROOT/bin/spicemedia"
upsert_env SPICE_QNN_CORE_BIN "$ROOT/runtime/bin/spice-qnn-core"
upsert_env SPICE_QNN_LIB_DIR "$ROOT/runtime/lib"
upsert_env SPICE_QNN_LOG "$ROOT/data/spicemedia/qnn-core.log"
upsert_env SPICE_QNN_HOST 127.0.0.1
upsert_env SPICE_QNN_PORT 18081
upsert_env SPICE_FACE_EMBED_MODEL "$ROOT/models/face/arcface_w600k_r50.bin"
upsert_env SPICE_FACE_DETECT_MODEL "$ROOT/models/face/scrfd_10g.bin"
upsert_env SPICE_IDENTITY_GENERATOR "${SPICE_IDENTITY_GENERATOR:-local-dream}"
upsert_env LOCAL_DREAM_URL "${LOCAL_DREAM_URL:-http://127.0.0.1:8081}"
upsert_env SPICE_ONNXRUNTIME_LIB "${SPICE_ONNXRUNTIME_LIB:-$ROOT/runtime/lib/libonnxruntime.so}"
upsert_env SPICE_INSWAPPER_MODEL "${SPICE_INSWAPPER_MODEL:-$ROOT/models/face/inswapper_128.onnx}"
upsert_env SPICE_IDENTITY_THRESHOLD "${SPICE_IDENTITY_THRESHOLD:-0.82}"
upsert_env SPICE_QUALITY_THRESHOLD "${SPICE_QUALITY_THRESHOLD:-0.78}"
upsert_env SPICE_IDENTITY_MAX_ATTEMPTS "${SPICE_IDENTITY_MAX_ATTEMPTS:-48}"
upsert_env SPICE_POSE_MAX_ATTEMPTS "${SPICE_POSE_MAX_ATTEMPTS:-4}"

echo
echo "Installing hoes launcher into Termux PATH..."
if [[ -n "${PREFIX:-}" && -d "$PREFIX/bin" ]]; then
  install -m 0755 "$ROOT/scripts/hoes" "$PREFIX/bin/hoes"
  echo "Installed: $PREFIX/bin/hoes"
else
  echo "PREFIX/bin unavailable; use $ROOT/scripts/hoes directly."
fi

echo
echo "Installed Go media runtime."
echo "Python is not required for spicemedia runtime; model conversion happens only in GitHub Actions."
echo "Then load config:"
echo "  set -a; source .env; set +a"
echo "Running health check..."
set -a
source .env
set +a
echo '{}' | ./bin/spicemedia health
