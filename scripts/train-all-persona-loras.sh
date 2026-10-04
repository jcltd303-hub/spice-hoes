#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for p in zara_voss ruby_wren tess_wilder celeste_vale lila_hart; do
  echo "==> training $p"
  PERSONA="$p" bash scripts/train-persona-lora.sh
done
echo "==> LoRAs: artifacts/loras/"
