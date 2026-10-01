#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${SPICE_GHOSTV2_DIR:-$HOME/ghostv2}"
command -v git >/dev/null || { echo "git is required" >&2; exit 2; }
command -v python >/dev/null || { echo "python is required" >&2; exit 2; }
if [ ! -d "$ROOT/.git" ]; then git clone --depth 1 https://github.com/dimitribarbot/ghostv2.git "$ROOT"; else git -C "$ROOT" pull --ff-only; fi
pkg install -y python-pillow libjpeg-turbo libpng openblas libandroid-execinfo 2>/dev/null || true
cd "$ROOT"
python -m pip install simple-parsing safetensors tqdm numpy opencv-python-headless scikit-image
python -m pip install transformers accelerate diffusers lightning || true
if [ -f requirements.txt ]; then python -m pip install -r requirements.txt || echo "Full upstream requirements include desktop/CUDA packages that may not build on Termux; preflight below will identify what remains." >&2; fi
python - <<'PY'
import importlib
mods=["simple_parsing","cv2","PIL","numpy","torch","safetensors","lightning","diffusers","transformers","skimage"]
missing=[]
for m in mods:
 try: importlib.import_module(m)
 except Exception as e: missing.append(f"{m}: {type(e).__name__}: {e}")
if missing:
 print("GhostV2 preflight FAILED:")
 print("\n".join(" - "+x for x in missing))
 raise SystemExit(4)
print("GhostV2 core import preflight OK")
PY
echo "GhostV2 dependencies passed core import preflight at $ROOT"
