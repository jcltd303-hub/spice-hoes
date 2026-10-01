#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v gh >/dev/null || { echo "GitHub CLI required: pkg install gh" >&2; exit 1; }

RUN_ID="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Face Embedding QNN" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"
if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
  echo "No successful face QNN build exists yet." >&2
  exit 1
fi

rm -rf .face-model-download
mkdir -p .face-model-download
gh run download "$RUN_ID" -R jcltd303-hub/spice-hoes -n spice-face-qnn-v75 -D .face-model-download

mkdir -p models/face
ARC="$(find .face-model-download -name arcface_w600k_r50.bin -type f -print -quit)"
DET="$(find .face-model-download -name scrfd_10g.bin -type f -print -quit)"
test -n "$ARC"
test -n "$DET"
cp "$ARC" models/face/arcface_w600k_r50.bin
cp "$DET" models/face/scrfd_10g.bin
find .face-model-download -name contracts.json -type f -exec cp {} models/face/ \; || true
find .face-model-download -name '*sha256.txt' -type f -exec cp {} models/face/ \; || true
rm -rf .face-model-download

echo "Installed:"
echo "  $ROOT/models/face/arcface_w600k_r50.bin"
echo "  $ROOT/models/face/scrfd_10g.bin"
echo
echo "export SPICE_FACE_EMBED_MODEL='$ROOT/models/face/arcface_w600k_r50.bin'"
echo "export SPICE_FACE_DETECT_MODEL='$ROOT/models/face/scrfd_10g.bin'"
