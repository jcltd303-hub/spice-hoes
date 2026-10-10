#!/usr/bin/env bash
set -euo pipefail
SPICE_TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SPICE_TASK_ROOT"
command -v gh >/dev/null || { echo 'Install gh and authenticate it to download workflow artifacts.' >&2; exit 2; }
SPICE_TASK_RUN="${SPICE_LLM_BUILD_RUN:-$(gh run list -R jcltd303-hub/spice-hoes --workflow build-llama-snapdragon.yml --branch "${SPICE_RUNTIME_BRANCH:-main}" --status success --limit 1 --json databaseId --jq '.[0].databaseId')}"
[[ -n "$SPICE_TASK_RUN" && "$SPICE_TASK_RUN" != null ]] || { echo 'Run Build S24 Snapdragon LLM in GitHub Actions first.' >&2; exit 2; }
SPICE_TASK_TMP="$(mktemp -d)"
trap 'rm -rf -- "$SPICE_TASK_TMP"' EXIT
gh run download "$SPICE_TASK_RUN" -R jcltd303-hub/spice-hoes -n spice-llama-snapdragon-arm64 -D "$SPICE_TASK_TMP"
test -s "$SPICE_TASK_TMP/llama-snapdragon.tar.gz"
(cd "$SPICE_TASK_TMP" && sha256sum -c SHA256SUMS)
mkdir -p runtime/llama-snapdragon
tar -xzf "$SPICE_TASK_TMP/llama-snapdragon.tar.gz" -C runtime/llama-snapdragon --strip-components=1
test -s runtime/llama-snapdragon/bin/llama-server
test -s runtime/llama-snapdragon/lib/libggml-htp-v75.so
chmod +x runtime/llama-snapdragon/bin/llama-*
echo 'Installed experimental Hexagon NPU/OpenCL LLM backend. start-local-llm.sh probes actual device availability.'
