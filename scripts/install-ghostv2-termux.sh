#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${SPICE_GHOSTV2_DIR:-$HOME/ghostv2}"
command -v git >/dev/null || { echo "git is required" >&2; exit 2; }
command -v python >/dev/null || { echo "python is required" >&2; exit 2; }
if [ ! -d "$ROOT/.git" ]; then git clone --depth 1 https://github.com/dimitribarbot/ghostv2.git "$ROOT"; else git -C "$ROOT" pull --ff-only; fi
pkg install -y python-numpy python-pillow libjpeg-turbo libpng openblas 2>/dev/null || pkg install -y python-numpy python-pillow libjpeg-turbo libpng openblas
cd "$ROOT"
python -m pip install simple-parsing safetensors tqdm
python -m pip install --no-deps opencv-python-headless || true
python -m pip install transformers accelerate diffusers lightning || true
python - <<'PY'
import ast,importlib
from pathlib import Path
tree=ast.parse(Path("inference.py").read_text())
imports=sorted({n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n,ast.Import)} | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module})
print("GhostV2 inference imports:",", ".join(imports))
checks=["simple_parsing","PIL","numpy","torch","safetensors","diffusers","transformers"]
missing=[]
for m in checks:
 try: importlib.import_module(m)
 except Exception as e: missing.append(f"{m}: {type(e).__name__}: {e}")
if missing:
 print("GhostV2 preflight FAILED:")
 print("\n".join(" - "+x for x in missing))
 raise SystemExit(4)
print("GhostV2 core import preflight OK")
PY
echo "GhostV2 bootstrap completed at $ROOT"
