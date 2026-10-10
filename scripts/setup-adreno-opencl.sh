#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
[[ -n "${PREFIX:-}" && -d "$PREFIX/lib" ]] || { echo 'Run this setup in native Termux.' >&2; exit 2; }
SPICE_TASK_VENDOR="${SPICE_OPENCL_VENDOR_DIR:-/vendor/lib64}"
[[ -r "$SPICE_TASK_VENDOR/libOpenCL.so" && -s "$SPICE_TASK_VENDOR/libOpenCL.so" ]] || {
  printf 'Vendor OpenCL entry point is missing or inaccessible: %s/libOpenCL.so\n' "$SPICE_TASK_VENDOR" >&2
  echo 'Use SPICE_LLM_BACKEND=cpu while diagnosing the phone driver.' >&2
  exit 3
}
SPICE_TASK_INSTALL="$SPICE_TASK_ROOT/runtime/adreno-opencl"
mkdir -p "$SPICE_TASK_INSTALL/releases"
SPICE_TASK_STAGE="$(mktemp -d "$SPICE_TASK_INSTALL/.stage.XXXXXX")"
trap 'rm -rf -- "$SPICE_TASK_STAGE"' EXIT
mkdir -p "$SPICE_TASK_STAGE/lib"
# Adreno can dlopen its implementation rather than declaring it in DT_NEEDED.
# Keep these phone-owned libraries separate from every package-managed library.
SPICE_TASK_SOURCES=()
for SPICE_TASK_NAME in libOpenCL.so libOpenCL_adreno.so libOpenCL_Adreno.so libCB.so libadreno_utils.so libllvm-qcom.so libllvm-glnext.so; do
  if [[ -r "$SPICE_TASK_VENDOR/$SPICE_TASK_NAME" && -s "$SPICE_TASK_VENDOR/$SPICE_TASK_NAME" ]]; then
    cp -L -- "$SPICE_TASK_VENDOR/$SPICE_TASK_NAME" "$SPICE_TASK_STAGE/lib/$SPICE_TASK_NAME"
    SPICE_TASK_SOURCES+=("$SPICE_TASK_VENDOR/$SPICE_TASK_NAME")
  fi
done
ln -s libOpenCL.so "$SPICE_TASK_STAGE/lib/libOpenCL.so.1"
sha256sum -- "${SPICE_TASK_SOURCES[@]}" > "$SPICE_TASK_STAGE/SOURCE_SHA256SUMS"
SPICE_TASK_SEARCH="$SPICE_TASK_STAGE/lib:$PREFIX/lib:$SPICE_TASK_VENDOR:$SPICE_TASK_VENDOR/egl:/system/lib64"
printf 'Probing the phone OpenCL driver with isolated libraries from %s\n' "$SPICE_TASK_VENDOR"
if LD_LIBRARY_PATH="$SPICE_TASK_SEARCH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    timeout 30s "${PYTHON_BIN:-python3}" scripts/probe-opencl.py \
    --library libOpenCL.so > "$SPICE_TASK_STAGE/platform.json"; then
  cat "$SPICE_TASK_STAGE/platform.json"
else
  SPICE_TASK_STATUS=$?
  cat "$SPICE_TASK_STAGE/platform.json"
  printf 'OpenCL probe failed (exit %s); the existing installation was kept.\n' "$SPICE_TASK_STATUS" >&2
  echo 'Missing-library/symbol errors require the exact named dependency; error -1001 means no platform enumerated. A timeout or signal indicates driver failure.' >&2
  echo 'Use SPICE_LLM_BACKEND=cpu bash scripts/start-local-llm.sh for now.' >&2
  exit 3
fi
touch "$SPICE_TASK_STAGE/verified"
SPICE_TASK_ID="$(sha256sum "$SPICE_TASK_STAGE/SOURCE_SHA256SUMS" | cut -d ' ' -f1)"
SPICE_TASK_RELEASE="$SPICE_TASK_INSTALL/releases/$SPICE_TASK_ID"
if [[ ! -d "$SPICE_TASK_RELEASE" ]]; then
  mv -- "$SPICE_TASK_STAGE" "$SPICE_TASK_RELEASE"
fi
ln -s "releases/$SPICE_TASK_ID" "$SPICE_TASK_INSTALL/.current.$$"
mv -Tf -- "$SPICE_TASK_INSTALL/.current.$$" "$SPICE_TASK_INSTALL/current"
echo 'Adreno OpenCL GPU enumeration succeeded. The launcher will use this isolated driver for OpenCL.'
echo 'Start with SPICE_LLM_BACKEND=opencl SPICE_LLM_DEVICE= SPICE_LLM_GPU_LAYERS=99 bash scripts/start-local-llm.sh'
echo 'Model loading, kernel compilation, and a real response still need to succeed.'
