#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SOURCE_REPO="${LOCAL_DREAM_REPO:-jcltd303-hub/local-dream}"
SOURCE_WORKFLOW="${LOCAL_DREAM_WORKFLOW:-Android Identity Build}"
SOURCE_COMMIT="${LOCAL_DREAM_RUNTIME_COMMIT:-59b99bb9040645a7fa970e6c628a27500fed8a2a}"
ARTIFACT_NAME="${LOCAL_DREAM_RUNTIME_ARTIFACT:-local-dream-identity-basic-debug}"

command -v gh >/dev/null || { echo "GitHub CLI required: pkg install gh" >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip required: pkg install unzip" >&2; exit 1; }

echo "Finding successful local-dream runtime artifact for $SOURCE_COMMIT..."
RUN_ID="$(
  gh run list -R "$SOURCE_REPO"     --workflow "$SOURCE_WORKFLOW"     --status success     --limit 50     --json databaseId,headSha     --jq ".[] | select(.headSha == \"$SOURCE_COMMIT\") | .databaseId"     | head -n1
)"

if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
  echo "No successful $SOURCE_WORKFLOW run found for $SOURCE_COMMIT" >&2
  exit 1
fi

echo "Using local-dream run $RUN_ID"
rm -rf .local-dream-runtime-download runtime
mkdir -p .local-dream-runtime-download runtime/bin runtime/lib

gh run download "$RUN_ID"   -R "$SOURCE_REPO"   -n "$ARTIFACT_NAME"   -D .local-dream-runtime-download

APK="$(find .local-dream-runtime-download -type f -name '*.apk' -print -quit)"
if [[ -z "$APK" ]]; then
  echo "Downloaded artifact contains no APK" >&2
  exit 1
fi

echo "Extracting native QNN runtime from $(basename "$APK")"
unzip -p "$APK" lib/arm64-v8a/libstable_diffusion_core.so > runtime/bin/spice-qnn-core
chmod +x runtime/bin/spice-qnn-core

rm -rf .local-dream-runtime-unpack
mkdir -p .local-dream-runtime-unpack
unzip -q "$APK" "assets/qnnlibs/*" -d .local-dream-runtime-unpack
cp .local-dream-runtime-unpack/assets/qnnlibs/* runtime/lib/

printf "%s\n" "$SOURCE_COMMIT" > runtime/NATIVE_CORE_COMMIT
printf "%s\n" "$RUN_ID" > runtime/SOURCE_RUN_ID
printf "%s\n" "$SOURCE_REPO" > runtime/SOURCE_REPO

test -s runtime/bin/spice-qnn-core
test -s runtime/lib/libQnnHtp.so
test -s runtime/lib/libQnnSystem.so
test -s runtime/lib/libQnnHtpV75Stub.so
test -s runtime/lib/libQnnHtpV75Skel.so

rm -rf .local-dream-runtime-download .local-dream-runtime-unpack

echo "Installed reused local-dream runtime:"
echo "  $ROOT/runtime/bin/spice-qnn-core"
echo "  $ROOT/runtime/lib/"
echo "Source:"
echo "  $SOURCE_REPO run $RUN_ID @ $SOURCE_COMMIT"
