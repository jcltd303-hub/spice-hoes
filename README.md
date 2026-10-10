# Spice Hoes experiment core

> Canonical implementation map: [docs/architecture.md](docs/architecture.md). Older Local Dream/textual-inversion notes are benchmark or legacy paths unless that architecture document says otherwise.

Runnable experiment loop for a portfolio of **fictional adult** AI influencers. The repo includes an append-only SQLite evidence ledger, versioned personas, a human approval gate, RAG project memory, a true mixture-of-agents (MoA) deliberation path, a gated Deep-Q learner for later-stage allocation, OpenAI-compatible MoA text inference, and a native S24 Go/QNN media-and-identity runtime.

The operating objective follows [project.md](project.md): optimize attributable net revenue while accounting for production/distribution cost, refunds, repeat purchase, retention, platform constraints, and evidence quality. Generated recommendations remain proposals until approved.

Device setup: [S24 GPU/NPU and offline voice](docs/s24-local-runtime.md). Heavy media: [free GPU notebook batches](docs/free-gpu-media.md).

The [income swarm launcher](docs/income-swarm.md) connects local S24 MoA planning, native S24 generation, owner-authorized scored release, durable publishing, signed live Stripe receipts, and corrected learning in a supervised loop. Start with `swarm-status`; unconfigured providers block production. The first unattended lane produces Instagram still images, with views kept separate from impressions and cost reservations kept separate from verified money.

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

Only approved knowledge is retrieved by the MoA path. Retrieval is lexical by default and upgrades to hybrid lexical + semantic search when an OpenAI-compatible embedding model is configured. Stored embeddings retain their model identifier so old knowledge can be backfilled or re-embedded deliberately. Every inserted item and every deliberation is logged.

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
export MOA_EMBEDDING_MODEL='YOUR-EMBEDDING-MODEL'
python3 -m spicecore.cli knowledge-backfill
python3 -m spicecore.cli knowledge-search "fashion garment performance"
```

If the embedding deployment is not configured, the same commands continue using deterministic lexical retrieval.

### Auditing the knowledge base

`knowledge-audit` runs a read-only audit over the live `knowledge` table: inventory by
source/approval/embedding model, `knowledge_added` provenance cross-checks, a
prompt-injection scan (bodies are injected verbatim into MoA expert prompts, so
instruction-like text is flagged high severity), staleness, near-duplicate detection,
truncation risk against the context budget, and retrieval probes against the top tags:

```bash

python3 -m spicecore.cli knowledge-audit --stale-days 180

python3 -m spicecore.cli knowledge-audit --probes "conversion;donations"

```

Findings carry severities (high/medium/low/info); the audit never modifies the ledger.
Note: `knowledge-add` approves items on insert — there is currently no separate review
step, so treat the audit's unapproved-item and injection findings as the review loop.

## Mixture of Agents

Set the OpenAI-compatible MoA provider outside the repository:

```bash
export MOA_BASE_URL='https://openrouter.ai/api/v1'
export MOA_API_KEY='YOUR_OPENROUTER_KEY'
export MOA_MODEL='openrouter/free'
```

Then run:

```bash
python3 -m spicecore.cli moa \
  "Choose the next measurable content experiment that maximizes expected net revenue" \
  --persona zara_voss
```

MoA v1 runs four independent experts in parallel—revenue, creative, growth, and risk—then sends those outputs to a fifth aggregator. Retrieval references, expert outputs, provider identity, and synthesis are recorded in the event ledger. The system never stores or fabricates hidden chain-of-thought.

## Asset generation

The canonical production media lane is the native S24 Go/QNN runtime described below. Generated images are persisted under ignored `data/assets/`, receive sidecar metadata and identity/quality scores, become review candidates, and append auditable generation events. The older Python `LocalDreamProvider` remains a benchmark-compatible adapter, not the production default.

The following Python CLI example exercises the compatibility/benchmark adapter, not the canonical native media path:

```bash
export LOCAL_DREAM_URL='http://127.0.0.1:8081'

python3 -m spicecore.cli generate \
  --persona zara_voss \
  --theme city-nights \
  --scene 'mirror selfie before a night-market set' \
  --channel Instagram \
  --offer affiliate \
  --seed 42
```

Compatibility-adapter batch across all five personas:

```bash
python3 -m spicecore.cli generate-batch \
  --theme outfit-choice \
  --channel TikTok \
  --offer affiliate \
  --count-per-persona 3 \
  --seed 1000
```

Every generated file remains `proposed` until a human approves it. The prompt builder carries forward the persona's adult status and visual identity anchors, adds realism/identity-consistency instructions, and rejects non-adult/non-fictional persona records.

### Identity master builder

`identity-master` builds the character identity master through the configured media lane
(LocalDream over HTTP, or native Go/QNN backed by the `cyber_realistic_v10` safetensors —
see `scripts/download-cyberrealistic-xl-desire.sh` and `SPICE_QNN_MODEL_DIR`):

```bash

python3 -m spicecore.cli identity-master --persona zara_voss --seed 42

```

It generates 9 views from the persona's `identity_reference` spec (4 portrait closeups +
eye closeup, 4 full-body rotations: front/left/right/back), composites the portrait board
(2x2 grid with the eye closeup dead center), scores every face-detectable view with the
IdentityGate, and promotes the pack to `data/references/<persona_id>/` split into `gate/`
(ArcFace-stable) and `conditioning/` (visual continuity only). Every view score and the
promotion are recorded in the ledger. Personas must be fictional adults or generation is
refused; use `--no-promote` to generate and composite without gating.

## Media-provider compatibility

The native Go/QNN S24 path is the production media lane. `spicecore.providers.LocalDreamProvider` may still be used as an optional comparison/legacy adapter where useful, but documentation and acceptance tests should not treat it as authoritative. Generated assets and identity packs stay in private/ignored storage.

The OpenAI-compatible MoA provider is the text-reasoning lane; the native S24 runtime is the image/identity lane. Provider interfaces remain small so deployments can change without rewriting experiment logic.

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

### Guarded auto-responder

`auto-respond` wires the pipeline end to end (ingest → draft → validate → approve → outbox) with the guards enforced in code:

```bash

python3 -m spicecore.cli auto-respond \
 --persona zara_voss \
 --channel Instagram \
 --conversation-id conv-123 \
 --message-id msg-456 \
 --body "What product is that?"

# or process every inbound message with no draft yet:
python3 -m spicecore.cli auto-respond --persona zara_voss --poll

```

Every draft is policy-validated before approval: identity deception, pressure tactics, payment-detail requests, guaranteed claims, shouting, and spam all
hold the draft for human review instead of sending. The persona disclosure is mandatory — appended automatically if the draft lacks it. The model's own
`handoff_reason` is respected, auto-approvals are rate-limited per conversation (default 10/day, `--max-per-day`), and every approval and hold is
audit-logged (`auto_reply_approved` / `auto_reply_held`). The auto path is text only: generated images stay on the human-reviewed generate → review →
approve path, and nothing failing validation ever reaches the outbox.

## Nextdoor campaign adapter

`spicecore.distribution.NextdoorPublisher` is a manual-handoff adapter: Nextdoor exposes no public posting API for neighborhood accounts, so the adapter
never auto-publishes. `publish()`/`schedule()` validate the copy against the engagement policy and fail closed with a staged handoff (copy + posting
checklist); the operator posts by hand from the verified account and records the URL with `publish`, then logs outcomes with `outcome`.

Generate a seeded, deterministic campaign (story / offer / event variants) and propose each variant as a review candidate:

```bash

python3 -m spicecore.cli campaign \
 --persona zara_voss \
 --goal "raise funds for the community fridge" \
 --cause "the Maple Street community fridge" \
 --neighborhood Maplewood \
 --offer https://example.org/fridge-fund \
 --seed 42

```

Every variant carries the persona disclosure and is policy-checked before it is proposed; any violation aborts the run. Generated copy never claims to be a
real neighbor, never makes guaranteed-earnings claims, never pressures readers, and never requests payment details. Candidates remain `proposed` until a
human approves them in the review desk.

### MoA-engineered donation campaigns

`campaign-moa` runs the deterministic generator above, then puts the variants through the Mixture-of-Agents deliberation (revenue, creative, growth, and
risk experts plus the aggregator). The MoA returns an engineered plan: variant ranking, concrete copy refinements, risk flags, one engineered post, and a
measurement design (test plan, success metrics, reversal condition).

```bash

export MOA_BASE_URL='https://openrouter.ai/api/v1'

export MOA_API_KEY=<redacted>

python3 -m spicecore.cli campaign-moa \
 --persona zara_voss \
 --goal "raise funds for the community fridge" \
 --cause "the Maple Street community fridge" \
 --neighborhood Maplewood \
 --offer https://example.org/fridge-fund \
 --seed 42

```

MoA output is advisory, never authoritative: the engineered post is re-validated against the copy policy and is only proposed when clean (dirty copy is
reported, not proposed). The deliberation is recorded as a `moa_deliberation` event and the plan as `campaign_engineered`. The MoA is instructed that no
outcome may be promised or guaranteed — everything is a hypothesis to be measured via the `outcome` loop.

### GoldDigger optimizer

`gold-digger` administers live donation campaigns. It reads published candidates and their recorded outcomes from the ledger, scores each variant as a
"vein" (impressions, clicks, donations, net), and runs Thompson sampling over donation-cents per impression to recommend the next move:

```bash

python3 -m spicecore.cli gold-digger --goal "fridge drive" --seed 11

```

Each vein gets a transparent verdict — `scale` (proven leader, double down), `explore` (not enough evidence yet), or `retire` (dry at real exposure) —
plus selection probabilities with 95% credible intervals and a concrete `next_action` ("post the story variant next; retire the event variant"). Every
report is recorded as a `gold_digger_report` event. A `purchase` outcome on a published candidate counts as a donation; the optimizer only reallocates
effort toward what measurably works. It never fabricates outcomes, never pressures donors, and never auto-posts.

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
  --external-id order-456 --amount-cents 900

python3 -m spicecore.cli offer-performance OFFER_ID
```

Manual purchase/refund imports require an explicit observed amount; expected payouts remain estimates. These imports appear in the general ledger but cannot assert verified earnings for the production swarm. Signed live Stripe receipts enter its verified money ledger. Variable commerce cost is recorded separately from distribution spend, and external event IDs keep imports idempotent. The current monetary ledger supports USD only.

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


## Native Go media runtime

The device media runtime is Go + native QNN/HTP only. Python is not required on the S24 for generation, face detection, alignment, embedding, or scoring. Python exists only inside the isolated GitHub Actions model-conversion workflow because Qualcomm's `qnn-onnx-converter` is itself a Python entry point.

Build the Go tools:

```bash
./scripts/build-go-tools.sh
```

For a clean Termux media setup with no Python dependency:

```bash
./scripts/setup-go-termux.sh
```

Runtime layout:

```text
bin/spicemedia
runtime/bin/spice-qnn-core
runtime/lib/libQnnHtp.so
runtime/lib/libQnnSystem.so
models/face/arcface_w600k_r50.bin
models/face/scrfd_10g.bin
spice-models/<generation-model>/
```

The runtime path is:

```text
spicemedia (Go)
  -> spice-qnn-core (native C++)
  -> Qualcomm QNN / Hexagon HTP
```

Face identity uses SCRFD detection + five-point alignment + ArcFace embeddings. The Go runtime exposes `detect`, `embed`, `identity`, `quality`, `generate`, and `health`.

Configure the Go media lane:

```bash
export SPICE_MEDIA_PROVIDER=go
export SPICE_MEDIA_BIN=bin/spicemedia
export SPICE_QNN_CORE_BIN=runtime/bin/spice-qnn-core
export SPICE_QNN_LIB_DIR=runtime/lib
export SPICE_QNN_MODEL_DIR="$HOME/spice-models/cyber_realistic_v10"
export SPICE_FACE_EMBED_MODEL=models/face/arcface_w600k_r50.bin
export SPICE_FACE_DETECT_MODEL=models/face/scrfd_10g.bin
export SPICE_QNN_TYPE=sd15npu
export SPICE_QNN_PORT=18081
```

The two heavyweight native/model artifacts are intentionally built on demand so ordinary CI remains fast:

```bash
./scripts/build-native-artifacts.sh
```

After both workflows succeed:

```bash
./scripts/install-spicemedia-termux.sh
set -a
source .env.spicemedia
set +a
```

Check the runtime:

```bash
echo '{}' | ./bin/spicemedia health
```

Local Dream may remain installed as an optional benchmark/legacy baseline; it is not required by the Go/QNN runtime and is not the canonical production path. See `docs/architecture.md`.
