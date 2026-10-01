#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v gh >/dev/null || { echo "GitHub CLI required: pkg install gh" >&2; exit 1; }

RUN_ID="$(gh run list -R jcltd303-hub/spice-hoes --workflow "Build Face Embedding QNN" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"
if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
  echo "No successful face embedding QNN build exists yet." >&2
  exit 1
fi

rm -rf .face-model-download
mkdir -p .face-model-download
gh run download "$RUN_ID" -R jcltd303-hub/spice-hoes -n spice-arcface-qnn-v75 -D .face-model-download
mkdir -p models/face
FOUND="$(find .face-model-download -name arcface_w600k_r50.bin -type f -print -quit)"
test -n "$FOUND"
cp "$FOUND" models/face/arcface_w600k_r50.bin
find .face-model-download -name arcface_contract.env -type f -exec cp {} models/face/ \; || true
find .face-model-download -name source_onnx_sha256.txt -type f -exec cp {} models/face/ \; || true
rm -rf .face-model-download

echo "Installed: $ROOT/models/face/arcface_w600k_r50.bin"
echo "export SPICE_FACE_EMBED_MODEL='$ROOT/models/face/arcface_w600k_r50.bin'"
