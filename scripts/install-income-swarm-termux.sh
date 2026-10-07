#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
if ! command -v pkg >/dev/null; then
  echo 'This installer runs in Termux. On Azure/Linux supervise scripts/run-income-swarm.sh with your service manager.' >&2
  exit 2
fi
pkg install -y python termux-services
python3 -m pip install -r requirements.txt
mkdir -p data/backups data/swarm-logs
[[ -f .env.swarm ]] || cp config/swarm.env.example .env.swarm
[[ -f data/swarm.json ]] || cp config/swarm.example.json data/swarm.json
chmod 600 .env.swarm data/swarm.json
chmod +x scripts/run-income-swarm.sh
SPICE_TASK_SERVICE="${PREFIX:?}/var/service/spice-income-swarm"
mkdir -p "$SPICE_TASK_SERVICE/log"
# Shell-quote the existing checkout path, including unusual path characters.
printf '#!/usr/bin/env bash\nset -e\ncd %q\nexec ./scripts/run-income-swarm.sh 2>&1\n' "$SPICE_TASK_ROOT" > "$SPICE_TASK_SERVICE/run"
printf '#!/usr/bin/env bash\nexec svlogd -tt %q\n' "$SPICE_TASK_ROOT/data/swarm-logs" > "$SPICE_TASK_SERVICE/log/run"
chmod +x "$SPICE_TASK_SERVICE/run" "$SPICE_TASK_SERVICE/log/run"
touch "$SPICE_TASK_SERVICE/down"
echo 'Installed stopped. Fill .env.swarm and data/swarm.json, then run scripts/run-income-swarm.sh --once.'
echo 'After the status has no blockers, start with: sv-enable spice-income-swarm'
