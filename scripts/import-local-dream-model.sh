#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="${LOCAL_DREAM_PACKAGE:-io.github.xororz.localdream}"
MODEL_ID="${1:-}"
DEST_ROOT="${2:-$HOME/spice-models}"

command -v adb >/dev/null || { echo "adb is required (pkg install android-tools)" >&2; exit 1; }
adb get-state >/dev/null

mkdir -p "$DEST_ROOT"

list_models() {
  adb shell "run-as $PKG sh -c 'cd files/models 2>/dev/null && ls -1d */ 2>/dev/null'" \
    | tr -d '\r' | sed 's#/$##' | sed '/^$/d'
}

export_one() {
  local model="$1"
  local tarname="spice-model-${model}.tar"

  echo "Exporting files/models/$model from $PKG..."
  adb shell "run-as $PKG sh -c 'cd files/models && tar -cf ../$tarname "$model"'"
  adb shell "run-as $PKG cat files/$tarname" > "$DEST_ROOT/$tarname"
  tar -xf "$DEST_ROOT/$tarname" -C "$DEST_ROOT"
  rm -f "$DEST_ROOT/$tarname"
  adb shell "run-as $PKG rm -f files/$tarname" >/dev/null 2>&1 || true

  test -d "$DEST_ROOT/$model"
  echo "Imported: $DEST_ROOT/$model"
}

if [[ -n "$MODEL_ID" ]]; then
  export_one "$MODEL_ID"
else
  mapfile -t MODELS < <(list_models)
  if (( ${#MODELS[@]} == 0 )); then
    echo "No Local Dream models found under $PKG/files/models" >&2
    exit 1
  fi
  echo "Found ${#MODELS[@]} Local Dream model(s): ${MODELS[*]}"
  for model in "${MODELS[@]}"; do
    export_one "$model"
  done
fi

SELECTED=""
for dir in "$DEST_ROOT"/*; do
  [[ -d "$dir" ]] || continue
  ok=1
  for required in tokenizer.json clip_v2.mnn pos_emb.bin token_emb.bin unet.bin vae_decoder.bin; do
    [[ -s "$dir/$required" ]] || { ok=0; break; }
  done
  if (( ok )); then
    SELECTED="$dir"
    break
  fi
done

if [[ -z "$SELECTED" ]]; then
  echo "Models were copied, but no complete sd15npu package was found." >&2
  echo "Expected: tokenizer.json clip_v2.mnn pos_emb.bin token_emb.bin unet.bin vae_decoder.bin" >&2
  exit 3
fi

ENV_FILE="$ROOT/.env.spicemedia"
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^SPICE_QNN_MODEL_DIR=' "$ENV_FILE"; then
    sed -i "s#^SPICE_QNN_MODEL_DIR=.*#SPICE_QNN_MODEL_DIR=$SELECTED#" "$ENV_FILE"
  else
    printf '\nSPICE_QNN_MODEL_DIR=%s\n' "$SELECTED" >> "$ENV_FILE"
  fi
else
  printf 'SPICE_QNN_MODEL_DIR=%s\n' "$SELECTED" > "$ENV_FILE"
fi

echo
echo "Selected generation model:"
echo "  $SELECTED"
echo
echo "Updated:"
echo "  $ENV_FILE"
echo
echo "Reload with:"
echo "  set -a; source .env.spicemedia; set +a"
echo "Then:"
echo "  echo '{}' | ./bin/spicemedia health"
