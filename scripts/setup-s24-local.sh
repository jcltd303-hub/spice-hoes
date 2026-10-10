#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
command -v pkg >/dev/null || { echo 'Run this setup in Termux.' >&2; exit 2; }
pkg install -y python python-pillow git curl ffmpeg llama-cpp vulkan-loader-android
if apt-cache show llama-cpp-backend-vulkan >/dev/null 2>&1; then
  pkg install -y llama-cpp-backend-vulkan
fi
python3 -m pip install 'PyYAML>=6,<7' 'rich>=13.9,<15'
mkdir -p models/llm data/public-media data/swarm-logs
[[ -f .env.swarm ]] || cp config/swarm.env.example .env.swarm
[[ -f data/swarm.json ]] || cp config/swarm.example.json data/swarm.json
chmod 600 .env.swarm data/swarm.json
if [[ -n "${SPICE_LLM_MODEL_URL:-}" ]]; then
  [[ "$SPICE_LLM_MODEL_URL" == https://* ]] || { echo 'Model URL must use HTTPS.' >&2; exit 2; }
  SPICE_TASK_MODEL="${SPICE_LLM_MODEL:-$SPICE_TASK_ROOT/models/llm/phone.gguf}"
  mkdir -p "$(dirname -- "$SPICE_TASK_MODEL")"
  curl --fail --location --retry 3 "$SPICE_LLM_MODEL_URL" -o "$SPICE_TASK_MODEL.part"
  python3 - "$SPICE_TASK_MODEL.part" <<'PY'
from pathlib import Path
import sys
with Path(sys.argv[1]).open('rb') as f:
    if f.read(4) != b'GGUF':
        raise SystemExit('Download is not a GGUF model')
PY
  mv -- "$SPICE_TASK_MODEL.part" "$SPICE_TASK_MODEL"
  printf 'SPICE_LLM_MODEL=%q\n' "$SPICE_TASK_MODEL" > .env.s24
  chmod 600 .env.s24
fi
echo 'Local tools installed. Set SPICE_LLM_MODEL to your GGUF or pass SPICE_LLM_MODEL_URL during setup.'
echo 'Start the model: bash scripts/start-local-llm.sh'
echo 'Open the updated Android companion for offline voice; keep it visible for microphone turns.'
echo 'Then: bash scripts/s24-doctor.sh'
