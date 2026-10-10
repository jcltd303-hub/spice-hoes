#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
for SPICE_TASK_ENV in .env .env.spicemedia .env.swarm .env.s24; do
  if [[ -f "$SPICE_TASK_ENV" ]]; then
    set -a
    source "$SPICE_TASK_ENV"
    set +a
  fi
done
exec "${PYTHON_BIN:-python3}" -m spicecore.cli --json compute-status
