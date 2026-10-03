#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$PWD}"
VENV="${LOCAL_MEDIA_VENV:-$ROOT/.venv-media}"

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "piper-tts>=1.3,<2"

if [ ! -d "$ROOT/vendor/MuseTalk/.git" ]; then
  mkdir -p "$ROOT/vendor"
  git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git "$ROOT/vendor/MuseTalk"
fi

"$VENV/bin/pip" install -r "$ROOT/vendor/MuseTalk/requirements.txt"

echo "Local media runtime installed."
echo "PIPER_BIN=$VENV/bin/piper"
echo "MUSETALK_DIR=$ROOT/vendor/MuseTalk"
echo "Download Piper voice ONNX/config and MuseTalk 1.5 model weights before rendering."
