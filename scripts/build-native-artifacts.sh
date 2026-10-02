#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="jcltd303-hub/spice-hoes"

command -v gh >/dev/null || {
  echo "GitHub CLI required: pkg install gh" >&2
  exit 1
}

echo "Native runtime already exists in local-dream; no rebuild needed."
echo "Installing reused runtime artifact..."
bash scripts/install-local-dream-runtime.sh

echo
echo "Triggering ArcFace + SCRFD QNN model build only..."
gh workflow run "Build Face Embedding QNN" -R "$REPO"

echo
echo "Runtime installed locally from local-dream."
echo "Face model workflow triggered."
echo "Watch it with:"
echo "  gh run list -R $REPO --workflow \"Build Face Embedding QNN\" --limit 5"
echo
echo "After face build succeeds:"
echo "  ./scripts/install-spicemedia-termux.sh"
