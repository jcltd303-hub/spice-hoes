#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO="${SPICE_REPO:-jcltd303-hub/spice-hoes}"
WORKFLOW="${SPICE_RUNTIME_WORKFLOW:-Build Spice QNN Runtime}"
ARTIFACT="${SPICE_RUNTIME_ARTIFACT:-spice-qnn-runtime-arm64}"

command -v gh >/dev/null || { echo "GitHub CLI required: pkg install gh" >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip required: pkg install unzip" >&2; exit 1; }

RUN_ID="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --status success --limit 1 --json databaseId --jq '.[0].databaseId')"
if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
  echo "No successful '$WORKFLOW' run found in $REPO" >&2
  exit 1
fi

TMP="$ROOT/.spice-runtime-download"
rm -rf "$TMP"
mkdir -p "$TMP"

echo "Downloading $ARTIFACT from $REPO run $RUN_ID"
gh run download "$RUN_ID" -R "$REPO" -n "$ARTIFACT" -D "$TMP"

CORE="$(find "$TMP" -type f -name 'spice-qnn-core' -print -quit)"
LIBROOT="$(dirname "$(find "$TMP" -type f -name 'libQnnHtp.so' -print -quit)")"
if [[ -z "$CORE" || ! -f "$CORE" ]]; then
  echo "Runtime artifact does not contain spice-qnn-core" >&2
  exit 1
fi
if [[ -z "$LIBROOT" || ! -d "$LIBROOT" ]]; then
  echo "Runtime artifact does not contain QNN libraries" >&2
  exit 1
fi

rm -rf runtime/bin runtime/lib
mkdir -p runtime/bin runtime/lib
cp "$CORE" runtime/bin/spice-qnn-core
chmod 0755 runtime/bin/spice-qnn-core
cp "$LIBROOT"/* runtime/lib/

for f in libQnnHtp.so libQnnSystem.so libQnnHtpV75Stub.so libQnnHtpV75Skel.so; do
  test -s "runtime/lib/$f" || { echo "Missing runtime/lib/$f" >&2; exit 1; }
done

printf "%s\n" "$RUN_ID" > runtime/SOURCE_RUN_ID
printf "%s\n" "$REPO" > runtime/SOURCE_REPO

rm -rf "$TMP"

echo "Installed Spice QNN runtime:"
echo "  $ROOT/runtime/bin/spice-qnn-core"
echo "  $ROOT/runtime/lib/"
echo "Source run: $RUN_ID"


# Keep the standalone Spice runtime self-contained for identity-aware generation.
if [[ -x "$ROOT/scripts/install-face-embedding-termux.sh" ]]; then
  echo
  echo "Installing latest face detector/embedding artifacts..."
  "$ROOT/scripts/install-face-embedding-termux.sh"
fi
