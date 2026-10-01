#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${SPICE_GHOSTV2_DIR:-$HOME/ghostv2}"
if ! command -v git >/dev/null; then echo "git is required" >&2; exit 2; fi
if ! command -v python >/dev/null; then echo "python is required" >&2; exit 2; fi
if [ ! -d "$ROOT/.git" ]; then git clone --depth 1 https://github.com/dimitribarbot/ghostv2.git "$ROOT"; else git -C "$ROOT" pull --ff-only; fi
echo "GhostV2 source installed at $ROOT"
echo "Its pretrained weights/source are BSD-3-Clause, but upstream currently uses PyTorch and does not provide the planned ONNX path."
echo "Do not install InsightFace/INSwapper as a fallback for commercial production."
