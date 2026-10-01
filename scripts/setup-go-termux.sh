#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/6] Installing Go/native runtime dependencies"
pkg install -y git gh golang jq curl unzip android-tools

echo "[2/6] Building Go media binaries"
chmod +x scripts/*
./scripts/build-go-tools.sh

echo "[3/6] Installing hoes launcher"
install -m 0755 scripts/hoes "$PREFIX/bin/hoes"

echo "[4/6] Checking GitHub authentication"
gh auth status

echo "[5/6] Checking native artifacts"
QNN_RUN="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Spice QNN Runtime" --status success --limit 1 --json databaseId --jq '.[0].databaseId' || true)"
FACE_RUN="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Face Embedding QNN" --status success --limit 1 --json databaseId --jq '.[0].databaseId' || true)"

if [[ -z "$QNN_RUN" || "$QNN_RUN" == "null" || -z "$FACE_RUN" || "$FACE_RUN" == "null" ]]; then
  echo "Native artifacts are not ready yet."
  echo "Trigger them with:"
  echo "  ./scripts/build-native-artifacts.sh"
  exit 2
fi

echo "[6/6] Installing Go/QNN runtime and face models"
./scripts/install-spicemedia-termux.sh

echo
echo "Go/native media setup complete."
echo "Python is not required for spicemedia runtime."
echo
echo "Load runtime environment:"
echo "  set -a; source .env.spicemedia; set +a"
echo
echo "Health:"
echo "  echo '{}' | ./bin/spicemedia health"
