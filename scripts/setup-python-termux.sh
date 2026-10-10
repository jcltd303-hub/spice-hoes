#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/3] Ensuring Python"
if ! command -v python3 >/dev/null; then
  pkg install -y python
fi
python3 --version

echo "[2/3] Installing Python dependencies"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "[3/3] Optional: Pillow (identity-master board compositing only)"
if ! python3 -c "import PIL" 2>/dev/null; then
  python3 -m pip install pillow || {
    echo "Pillow install failed; identity-master board compositing will be unavailable." >&2
    echo "Everything else in the Python control plane works without it." >&2
  }
fi

echo
echo "Smoke test: CLI help"
python3 -m spicecore.cli --help >/dev/null
echo "Python control plane ready."
echo
echo "Next:"
echo "  python3 -m spicecore.cli init"
echo "  python3 -m spicecore.cli briefs --theme outfit-choice --channel Instagram --seed 42"
echo "  python3 -m spicecore.cli doctor"
echo
echo "Full test suite (a few minutes on device):"
echo "  python3 -m unittest discover -s tests"
