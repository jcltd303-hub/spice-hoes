#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PKG="${LOCAL_DREAM_PACKAGE:-io.github.xororz.localdream}"
MODEL_ID="${1:-}"
DEST_ROOT="${2:-$HOME/spice-models}"

if [[ -z "$MODEL_ID" ]]; then
  echo "usage: $0 MODEL_ID [DEST_ROOT]" >&2
  exit 2
fi

command -v adb >/dev/null || { echo "adb is required (pkg install android-tools)" >&2; exit 1; }
adb get-state >/dev/null

mkdir -p "$DEST_ROOT"
TMP="/data/local/tmp/spice-model-${MODEL_ID}.tar"
REMOTE_REL="files/models/${MODEL_ID}"

echo "Exporting $REMOTE_REL from $PKG..."
adb shell "run-as $PKG sh -c 'cd files/models && tar -cf /data/data/$PKG/cache/spice-model.tar "$MODEL_ID"'"
adb shell "run-as $PKG cat cache/spice-model.tar" > "$DEST_ROOT/${MODEL_ID}.tar"
mkdir -p "$DEST_ROOT/$MODEL_ID"
tar -xf "$DEST_ROOT/${MODEL_ID}.tar" -C "$DEST_ROOT"
rm -f "$DEST_ROOT/${MODEL_ID}.tar"

echo "Model exported to: $DEST_ROOT/$MODEL_ID"
echo "export SPICE_QNN_MODEL_DIR='$DEST_ROOT/$MODEL_ID'"