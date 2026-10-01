# Spice Hoes experiment core

Runnable experiment loop for a portfolio of **fictional adult** AI influencers. The repo now includes an append-only SQLite evidence ledger, versioned personas, a human approval gate, RAG project memory, a true mixture-of-agents (MoA) deliberation path, a gated Deep-Q learner for later-stage allocation, Azure text inference, and a local-dream/S24 image adapter.

The operating objective follows [project.md](project.md): optimize attributable net revenue while accounting for production/distribution cost, refunds, repeat purchase, retention, platform constraints, and evidence quality. Generated recommendations remain proposals until approved.

## Start locally

Requires Python 3.11+ and PyYAML:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v

python3 -m spicecore.cli init
python3 -m spicecore.cli briefs --theme outfit-choice --channel Instagram --seed 42
python3 -m spicecore.cli recommend --seed 42
python3 -m spicecore.cli serve
```

`serve` prints a loopback URL with a random token. The review desk is local-only and records approve/revise/reject decisions; it does not publish by itself.

## RAG knowledge base

Only approved knowledge is retrieved by the MoA path. Retrieval is lexical by default and upgrades to hybrid lexical + semantic search when an Azure embedding deployment is configured. Stored embeddings retain their model identifier so old knowledge can be backfilled or re-embedded deliberately. Every inserted item and every deliberation is logged.

```bash
python3 -m spicecore.cli knowledge-add \
  --source ai_influencer_guide \
  --title "Mirror-video benchmark" \
  --body "Talking-head advice, mirror selfie outfits and product unboxings are the guide's highest-converting formats." \
  --tags content,conversion

python3 -m spicecore.cli knowledge-search "mirror outfits conversion"
```

Optional semantic retrieval:

```bash
export AZURE_OPENAI_EMBEDDING_DEPLOYMENT='YOUR-EMBEDDING-DEPLOYMENT'
python3 -m spicecore.cli knowledge-backfill
python3 -m spicecore.cli knowledge-search "fashion garment performance"
```

If the embedding deployment is not configured, the same commands continue using deterministic lexical retrieval.

## Mixture of Agents on Azure

Set Azure credentials outside the repository:

```bash
export AZURE_OPENAI_ENDPOINT='https://YOUR-RESOURCE.openai.azure.com'
export AZURE_OPENAI_API_KEY='...'
export AZURE_OPENAI_DEPLOYMENT='YOUR-DEPLOYMENT'
export AZURE_OPENAI_API_VERSION='2025-04-01-preview'
```

Then run:

```bash
python3 -m spicecore.cli moa \
  "Choose the next measurable content experiment that maximizes expected net revenue" \
  --persona zara_voss
```

MoA v1 runs four independent experts in parallel—revenue, creative, growth, and risk—then sends those outputs to a fifth aggregator. Retrieval references, expert outputs, provider identity, and synthesis are recorded in the event ledger. The system never stores or fabricates hidden chain-of-thought.

## Asset generation

The repo can now call the S24/local-dream endpoint directly, persist the returned image under ignored `data/assets/`, write a sidecar JSON record, create a review candidate, and append an `asset_generated` event.

Single asset:

```bash
export LOCAL_DREAM_URL='http://127.0.0.1:7860'

python3 -m spicecore.cli generate \
  --persona zara_voss \
  --theme city-nights \
  --scene 'mirror selfie before a night-market set' \
  --channel Instagram \
  --offer affiliate \
  --seed 42
```

Batch across all five personas:

```bash
python3 -m spicecore.cli generate-batch \
  --theme outfit-choice \
  --channel TikTok \
  --offer affiliate \
  --count-per-persona 3 \
  --seed 1000
```

Every generated file remains `proposed` until a human approves it. The prompt builder carries forward the persona's adult status and visual identity anchors, adds realism/identity-consistency instructions, and rejects non-adult/non-fictional persona records.

## Local-dream / S24 media lane

`spicecore.providers.LocalDreamProvider` is the only image-generation adapter in this branch. It defaults to `http://127.0.0.1:7860/generate` and accepts `LOCAL_DREAM_URL` and optional `LOCAL_DREAM_TOKEN`. Generated assets should be persisted to private storage and then registered with `propose`; do not commit identity references or private generated assets.

Azure is the text-reasoning lane; local-dream on the S24 is the image lane. Provider interfaces remain small so deployments can change without rewriting experiment logic.

## DeepRL

`spicecore.deeprl.DeepRLPolicy` implements a small one-hidden-layer DQN-style value network over portfolio state. It stores explicit state/action/reward/next-state transitions in SQLite, persists versioned policy snapshots across process restarts, and is deliberately gated by `min_experiences` (128 by default). Until the replay buffer reaches that threshold, the existing contextual bandit remains the allocation policy.

That gate is intentional: the project does not call sparse early observations “DeepRL.” Once enough transitions exist, training and decisions are themselves recorded as `rl_training_completed` and `rl_policy_decision` events.

## Reviewed publish/outcome loop

```bash
python3 -m spicecore.cli propose --persona zara_voss --theme city-nights --format still --channel test --offer set --asset-uri assets/example.png --prompt 'Original adult character on a neon street' --model local-dream --seed 12 --cost-cents 20
python3 -m spicecore.cli review CANDIDATE_ID approved --reviewer operator
python3 -m spicecore.cli publish CANDIDATE_ID --url https://example.org/post
python3 -m spicecore.cli outcome CANDIDATE_ID impression --external-id impression-1
python3 -m spicecore.cli outcome CANDIDATE_ID purchase --amount-cents 500 --external-id payment-1
python3 -m spicecore.cli stats
python3 -m spicecore.cli events
```

Unique external IDs make outcome imports idempotent. Do not put private messages, payment-card data, API keys, identity reference packs, or generated adult assets in the repository.

## CI and next production adapters

GitHub Actions runs the unit suite on pushes and pull requests. Production still needs authenticated cloud review/email delivery, private object storage, permitted distribution adapters, and first-party commerce/outcome ingestion. Preserve human approval and the event trail while those adapters are added.
