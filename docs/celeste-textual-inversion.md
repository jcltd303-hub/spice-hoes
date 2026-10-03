# Celeste Vale textual inversion (legacy/benchmark path)

> This workflow is retained for reproducibility and benchmarking. It is **not** the canonical production identity path. Production uses native `spicemedia` -> QNN generation -> SCRFD -> five-point alignment -> ArcFace verification. See [architecture.md](architecture.md) and [master-references.md](master-references.md).

The optional Local Dream benchmark integration expects the identity token `cvceleste`. The imported file must therefore be named:

```text
cvceleste.safetensors
```

Local Dream SD1.5 textual inversions use 768-wide CLIP vectors and support multiple vectors per trigger. The training preset uses four vectors.

## Prepare

The trainer reads the verified pack from:

```text
data/references/celeste_vale/
```

and rejects the existing excluded categories (`master_*`, `contact_*`, and rear references).

```bash
python3 scripts/prepare-textual-inversion.py
```

The resulting manifest is:

```text
data/embedding-training/celeste_vale/manifest.json
```

## Train

Training requires a CUDA GPU. Install the isolated dependencies:

```bash
python3 -m venv .venv-ti
source .venv-ti/bin/activate
pip install -r requirements-textual-inversion.txt
accelerate config default
./scripts/train-textual-inversion.sh
```

Defaults:

- base family: SD1.5
- trigger: `cvceleste`
- initializer: `woman`
- vectors: 4
- steps: 2000
- learning rate: 5e-4
- resolution: 512
- seed: 20261002

Override any setting through environment variables, for example:

```bash
BASE_MODEL=/path/to/the/original-SD1.5-checkpoint-or-diffusers-model \
STEPS=2500 VECTORS=4 ./scripts/train-textual-inversion.sh
```

The final artifact is normalized to:

```text
artifacts/embeddings/cvceleste.safetensors
```

## Install and verify in Local Dream

Import `cvceleste.safetensors` in Local Dream's Embedding Manager. The patched Local Dream backend exposes its loaded inventory:

```bash
curl -s http://127.0.0.1:8081/embeddings | jq
```

If Local Dream was already running when the file was imported:

```bash
curl -s -X POST http://127.0.0.1:8081/embeddings/reload | jq
```

Then run `spicemedia identity-generate` with `require_identity_embedding: true`. The generation prompt automatically receives `(cvceleste:1.10)` before InSwapper and ArcFace verification.
