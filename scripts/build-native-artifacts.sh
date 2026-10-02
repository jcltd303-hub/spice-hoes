#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="jcltd303-hub/spice-hoes"

command -v gh >/dev/null || {
  echo "GitHub CLI required: pkg install gh" >&2
  exit 1
}

echo "Installing latest successful Spice QNN runtime artifact..."
bash scripts/install-spice-qnn-runtime-termux.sh

echo
echo "Installing latest successful ArcFace + SCRFD QNN artifact..."
bash scripts/install-face-embedding-termux.sh

echo
echo "Native artifacts installed."
echo "Load runtime environment with:"
echo "  set -a; source .env.spicemedia; set +a"
echo "Then run:"
echo "  echo '{}' | ./bin/spicemedia health"
