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

echo "[5/6] Installing Spice QNN runtime artifact"
bash scripts/install-spice-qnn-runtime-termux.sh

echo "[6/6] Installing Go/QNN runtime and face models"
FACE_RUN="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Face Embedding QNN" --status success --limit 1 --json databaseId --jq '.[0].databaseId' || true)"
if [[ -z "$FACE_RUN" || "$FACE_RUN" == "null" ]]; then
  echo "Face model artifact is not ready yet."
  echo "Trigger only the face model build with:"
  echo "  gh workflow run \"Build Face Embedding QNN\" -R jcltd303-hub/spice-hoes"
  exit 2
fi
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
