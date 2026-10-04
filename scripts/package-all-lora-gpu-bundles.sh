#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PERSONAS=(
  zara_voss
  ruby_wren
  tess_wilder
  celeste_vale
  lila_hart
)

for persona in "${PERSONAS[@]}"; do
  echo "==> extracting Canon face crops for $persona"
  PERSONA="$persona" bash scripts/extract-canon-faces.sh

  echo "==> packaging GPU LoRA bundle for $persona"
  PERSONA="$persona" bash scripts/package-lora-gpu-bundle.sh

done

echo
echo "==> all GPU LoRA bundles ready"
find artifacts/lora-training -maxdepth 1 -type f -name '*-gpu.tar.gz' -print | sort
