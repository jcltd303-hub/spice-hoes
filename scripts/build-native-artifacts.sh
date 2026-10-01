#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="jcltd303-hub/spice-hoes"

command -v gh >/dev/null || {
  echo "GitHub CLI required: pkg install gh" >&2
  exit 1
}

echo "Triggering standalone QNN runtime build..."
gh workflow run "Build Spice QNN Runtime" -R "$REPO"

echo "Triggering ArcFace + SCRFD QNN model build..."
gh workflow run "Build Face Embedding QNN" -R "$REPO"

echo
echo "Triggered both on-demand workflows."
echo "Watch them with:"
echo "  gh run list -R $REPO --limit 10"
echo
echo "After both succeed:"
echo "  ./scripts/install-spicemedia-termux.sh"
