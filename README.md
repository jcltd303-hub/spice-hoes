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


## Controlled autopilot and learning closure

The core autopilot can create a bounded experiment batch while respecting a daily generation budget and a maximum pending-review queue. It never publishes automatically.

```bash
python3 -m spicecore.cli autopilot-run \
  "Improve qualified affiliate conversion" \
  --channel TikTok \
  --offer affiliate \
  --variants 3 \
  --cost-cents-per-asset 25 \
  --max-pending-review 12 \
  --daily-budget-cents 5000
```

After variants have been reviewed, published by the distribution layer, and have sufficient exposure, close the run:

```bash
python3 -m spicecore.cli autopilot-settle RUN_ID --min-impressions 100
```

Settlement is idempotent. It records one state/action/reward/next-state transition for DeepRL, computes reward from observed net outcome, writes a source-tagged experiment summary into RAG, and marks the autopilot run settled. Published variants must meet the requested impression threshold; proposed or approved-but-unpublished variants block settlement.

## Reviewed engagement drafts

Inbound social messages can be ingested idempotently, redacted for obvious payment-card/email data, grounded against project knowledge, and drafted in the persona voice. Drafts are never sent automatically.

```bash
python3 -m spicecore.cli engagement-ingest \
  --persona zara_voss \
  --channel Instagram \
  --conversation-id conv-123 \
  --message-id msg-456 \
  --body "Are you AI? What product is that?"

python3 -m spicecore.cli engagement-draft \
  --persona zara_voss \
  --message-id INTERNAL_MESSAGE_ID

python3 -m spicecore.cli engagement-review DRAFT_ID approved \
  --reviewer operator

python3 -m spicecore.cli engagement-outbox
```

The draft policy keeps the fictional persona transparent: it must not claim to be a real human, pressure users to spend, imply spending proves affection, or request card/banking details. The approved outbox is intentionally separate from any platform send adapter.

## Offer economics and commerce attribution

Offers are first-class records with explicit type, expected payout, variable commerce cost, active state, and USD-denominated unit economics. Candidates can be linked to an offer with a unique tracking token.

```bash
python3 -m spicecore.cli offer-create \
  --name "Travel Tote Affiliate" \
  --kind affiliate \
  --expected-payout-cents 900 \
  --variable-cost-cents 100

python3 -m spicecore.cli offer-register CANDIDATE_ID OFFER_ID \
  --url https://shop.example/item

python3 -m spicecore.cli offer-event TRACKING_TOKEN click \
  --external-id click-123

python3 -m spicecore.cli offer-event TRACKING_TOKEN purchase \
  --external-id order-456

python3 -m spicecore.cli offer-performance OFFER_ID
```

Purchase events can use the offer's configured expected payout when no amount is supplied. Variable commerce cost is recorded separately from distribution spend and flows into persona stats, experiment results, and RL reward. External event IDs keep imports idempotent. The current monetary ledger is intentionally USD-only until explicit multi-currency conversion is added.

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

## Versioned runtime policy

Production limits are stored in an immutable, audited runtime policy rather than only in CLI defaults. The active policy controls:

```text
daily_budget_cents
max_pending_review
min_impressions_to_learn
rl_min_experiences
identity_threshold
quality_threshold
reference_strength
```

Inspect or change policy:

```bash
python3 -m spicecore.cli policy-show

python3 -m spicecore.cli policy-set \
  --set daily_budget_cents=2500 \
  --set quality_threshold=0.84 \
  --actor operator \
  --note "tighten production limits"

python3 -m spicecore.cli policy-history
```

Every change creates and activates a new policy version; old versions remain in the ledger for reproducibility. Autopilot and learning commands use the active version unless a run-level override is explicitly supplied.

## Operational health and backups

The core SQLite ledger now enables WAL mode, normal synchronous durability, foreign keys, and a 5-second busy timeout for safer concurrent local workers.

Run a production-readiness snapshot:

```bash
python3 -m spicecore.cli doctor
```

The doctor reports database integrity plus operational backlogs such as pending content review, unsettled autopilot runs, unembedded knowledge, engagement drafts, active offers, and RL readiness.

Create an online verified backup without stopping the process:

```bash
python3 -m spicecore.cli backup data/backups/experiments-$(date +%Y%m%d).sqlite
```

Backups are created through SQLite's backup API, checked with `PRAGMA quick_check`, hashed with SHA-256, and recorded in the event ledger. Existing backup paths are never overwritten.

## CI and next production adapters

GitHub Actions runs the unit suite on pushes and pull requests. Production still needs authenticated cloud review/email delivery, private object storage, permitted distribution adapters, and first-party commerce/outcome ingestion. Preserve human approval and the event trail while those adapters are added.
