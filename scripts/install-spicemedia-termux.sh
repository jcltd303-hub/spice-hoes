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

echo "[5/5] Writing local Go-media environment template"
cat > .env.spicemedia <<EOF
SPICE_MEDIA_PROVIDER=go
SPICE_MEDIA_BIN=$ROOT/bin/spicemedia
SPICE_QNN_CORE_BIN=$ROOT/runtime/bin/spice-qnn-core
SPICE_QNN_LIB_DIR=$ROOT/runtime/lib
SPICE_QNN_MODEL_DIR=$HOME/spice-models/cyber_realistic_v10
SPICE_QNN_TYPE=sd15npu
SPICE_QNN_HOST=127.0.0.1
SPICE_QNN_PORT=18081
SPICE_QNN_LOG=$ROOT/data/spicemedia/qnn-core.log
SPICE_FACE_EMBED_MODEL=$ROOT/models/face/arcface_w600k_r50.bin
SPICE_FACE_DETECT_MODEL=$ROOT/models/face/scrfd_10g.bin
EOF

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
echo "  set -a; source .env.spicemedia; set +a"
echo "Running health check..."
set -a
source .env.spicemedia
set +a
echo '{}' | ./bin/spicemedia health
