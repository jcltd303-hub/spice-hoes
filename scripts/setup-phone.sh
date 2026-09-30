#!/data/data/com.termux/files/usr/bin/bash
set -eu
# Installs local runtime only; no credentials, guessed cloud routes, or model downloads.
if ! command -v pkg >/dev/null 2>&1; then
  echo "Run this script inside Termux." >&2
  exit 1
fi
pkg install -y python termux-api
mkdir -p "$HOME/.local/share/spice-phone/checkpoints"
chmod 700 "$HOME/.local/share/spice-phone/checkpoints"
echo "Install/authorize the Termux:API app separately for device telemetry."
echo "Open Local Dream and load the owner-selected model manually."
echo "Record installed version/model/capabilities; configure the authenticated Azure adapter."
echo "Worker starts in dry-run. See docs/phone-worker.md before enabling a live canary."
