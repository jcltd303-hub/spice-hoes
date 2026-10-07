#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
if [[ -f .env.spicemedia ]]; then
  set -a
  source .env.spicemedia
  set +a
fi
if [[ ! -f .env.swarm ]]; then
  echo 'Create .env.swarm from config/swarm.env.example and configure data/swarm.json.' >&2
  exit 2
fi
set -a
source .env.swarm
set +a
exec "${PYTHON_BIN:-python3}" -m spicecore.cli --db "${SPICE_DB:-data/experiments.sqlite}" --json swarm-run "$@"
