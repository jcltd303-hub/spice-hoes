# Azure + S24 Ultra Mixture of Agents
Date: 2026-09-30
Status: proposed architecture for owner review; no production integrations activated.
Repository baseline: 20f00bb7198d932bea074a72d67b06b4594858d9

## Intent and constraints
Build a commercial operating loop for original disclosed adult fictional personas: research, generate, review, publish, engage, fulfill, measure, improve. Use Azure services funded by verified eligible credits and Local Dream on the owner's S24 Ultra exclusively for compute. GitHub stores source and CI only. No third-party inference fallback. Monetization and virality are hypotheses measured by experiments, never guaranteed outcomes. MoA means Mixture of Agents, not mixture-of-experts model training.

## Alternatives and decision
Recommended: explicit Python layered MoA with Azure-hosted model deployments, Azure durable jobs, and a phone pull worker. This extends the existing Python core and permits deterministic tests and budget accounting.
Alternative: managed Foundry agent workflows; higher service coupling and provisioning complexity.
Alternative: run all reasoning on the phone; Local Dream is an image backend, not a substitute for the required language agents.
Implement the recommended explicit orchestrator with replaceable Azure transport adapters.

## Layered MoA contract
An input includes task ID, persona/version, task type, retrieved evidence IDs, allowed actions, budget reservation, and requested deliverable.
Layer 1 makes independent proposals from research, creative, commerce, and persona specialists. Each is a separate Azure inference call. Applicable roles are selected by task type; unrelated roles do not run.
Layer 2 gives all proposals to evidence and quality critics. Critics identify unsupported claims, contradictions, missing citations, identity drift, fulfillment risks, and cost issues.
Layer 3 calls an aggregator with proposals, critiques, retrieved facts and original task. It emits structured decision JSON: chosen proposal, evidence IDs, alternatives, disagreement, action request, expected cost, and confidence qualifier.
Validate schemas and evidence references deterministically. Model-generated confidence is not a calibrated probability. Record deployment IDs, token usage, latency, prompts, outputs, layer membership and decision rationale. Do not record hidden chain-of-thought.
At least two independent proposers plus critic and aggregator are required for a successful MoA run. A partial or timed-out run fails closed for external actions. Different Azure deployments may supply diversity where available; do not falsely report distinct models when roles share a deployment.
Limit each run to three layers, explicit token limits, bounded timeout and retries. Reserve worst-case cost before execution; settle actual usage afterward. No recursively spawning agents.

## Knowledge base and RAG
Support add, revise, search, archive and delete operations for Markdown, text, JSON and approved extracted documents.
Separate namespaces: persona canon, offers/fulfillment, platform policies, licensed references, public research, experiment results, modeling opportunities, and private conversation memory.
Documents have immutable revision IDs, source URI, collection date, content hash, owner, rights, namespace, persona, sensitivity, expiry and evidence class: fictional canon, observed, inferred, hypothesis.
Chunk by headings and token bounds, preserving document and revision citation IDs. Development uses SQLite FTS5 with optional Azure embedding vectors; Azure production stores documents in Blob Storage and uses an Azure vector-capable search service only after credit eligibility and costs are confirmed.
Hybrid retrieval combines lexical and vector search when configured; lexical-only mode is explicitly reported. Apply tenant/persona/access/expiry filters BEFORE ranking. RAG answers cite retrieved chunks and abstain on missing facts.
Treat retrieved text and DMs as untrusted data, never instructions or tool authorization. Private conversation memories cannot enter public research or another customer's context. Deletion removes source, chunks, vectors and private text; audit records retain only non-sensitive IDs and operation metadata.
Promote successful experiments to knowledge with sample sizes, costs, attribution limits and outcome windows. Do not promote model-generated claims into observed facts.

## Azure and phone execution
Azure Functions or a small Azure container service hosts authenticated orchestration; Azure queues carry durable work; Blob Storage holds private assets and evidence. Use managed identities, short-lived scoped uploads, Key Vault and least-privilege roles.
Require subscription ID, active credit expiry, eligible service list, approved region/model deployment, owner-defined spending ceiling and capacity checks before provisioning or inference. Credits are funding, not proof of eligibility or unlimited capacity. Fail closed when eligibility or remaining budget cannot be verified; no paid fallback.
The S24 Termux worker polls authenticated jobs over outbound HTTPS, leases one generation job at a time and calls Local Dream on 127.0.0.1:8081 POST /generate. Parse SSE and bounded JSON error responses; validate encoded image size/type, hash output and upload via scoped URL.
Local Dream requires the app to load a model first. Probe the actual installed app/version and model; never invent a health endpoint or assume remote startup, LoRA or face-reference features. Keep the backend off the public network.
Use heartbeat, renewable leases, retry limits, deduplication and a dead-letter queue. Offline/thermal/low-battery states defer work, never route images to cloud inference. Record model, seed, supported settings, input reference hash and runtime. If generation finishes after lease loss, reconcile by job ID rather than repeat public delivery.
Identity consistency must pass the existing Celeste acceptance test. Img2img alone is not evidence of identity locking.
Video starts with original scripts and deterministic editing of phone-generated assets on Azure or phone. No external generative-video provider. Do not claim slideshow editing guarantees reward eligibility or virality.

## Autonomous workflows
Internal research, RAG retrieval, proposal generation, critiquing, job preparation, outcome ingestion and experiment allocation may execute autonomously within quotas.
External tools are centrally mediated, never available directly to specialist agents. Every action has idempotency key, account scope, policy version, rate cap and audit receipt.
Start in dry-run. Move a specific connector/action to live only after authentication, account ownership, platform permission, end-to-end test and explicit configured authorization. Content publishing starts with human review; automation can release only preapproved assets under a bounded schedule. New offers, public claims and contracts require review.
Operator controls include pause, emergency stop, daily quotas, approval queue, pending jobs, evidence browser and rollback of unpublished work. No self-modification of permissions, spend ceilings or historical observations.

## DMs
Support authenticated permitted inbound message ingestion and opt-out-aware conversation state. The requested character voice is charming, witty, selective, commercially savvy and luxury-minded.
Maintain disclosed fictional AI identity; no false real-world availability, romantic exclusivity, hardship stories, guilt, threats or manufactured personal emergencies to induce spending. Do not infer financial vulnerability or optimize extraction from it.
Ground pricing, inventory, delivery times and offers in current approved RAG facts. Support questions, paid-content inquiries and brand leads with clear purchase/fulfillment details.
Initial outbound mode is draft-only. Later authorize bounded replies per supported platform, with deduplication, cooldown, recipient allowlists, opt-out suppression and escalation. Uncertain age, disputes, sensitive messages, bespoke commitments and unsupported claims escalate.
This design does not send any DMs now; account access and connector validation are not available in the repository.

## Modeling and brand revenue
Create a virtual-model media kit, licensed sample portfolio, offer catalog and opportunity pipeline: discovered, qualified, drafted, owner-approved, sent, negotiating, contracted, fulfilled, paid.
Qualify leads for explicit acceptance of synthetic models, budget evidence, fit and rights. Offer campaign image collections, virtual product/editorial modeling and licensed original character assets. No promises of physical attendance.
Track deliverables, usage rights, term, territories, exclusivity, revisions, approvals, deposit, balance and fulfillment cost. Outreach and contractual commitments require owner review until a specific bounded workflow is authorized.

## TikTok experiments
Generate hook variants, storyboards, captions and original narrative series from persona canon. Begin with three content pillars per persona, versioned creative briefs and bounded batch sizes.
Record AI labeling and policy checks. Do not scrape or repost copyrighted trends or assume a publishing API permits unattended posting.
Measure qualified views, completion, shares, profile visits, attributed store visits, purchases and retained contribution. Store attribution uncertainty explicitly. Affiliate, sponsorship, memberships, collections and modeling are separate revenue streams; platform rewards are conditional.
No manufactured likes, followers, messages or earnings.

## Commerce and learning
Extend ledger with gross receipts, platform fees, refunds/chargebacks, inference, rejected generations, storage, distribution and operator labor. Track settled payouts separately from gross sales.
Add consent-compatible customer pseudonyms, cohort retention, renewal/repeat purchases, attribution method and time window. Do not store card data.
Replace persona-only net-per-post selection with comparable experiment arms and delayed outcome windows. Initially use bounded randomized exploration; do not claim contextual bandit or reinforcement learning until implemented and evaluated. Promote based on contribution and uncertainty rather than impressions alone.

## Delivery and verification
1. MoA schemas/orchestrator and RAG CRUD/retrieval; fake Azure transport tests plus explicit provider restrictions.
2. Azure inference transport and application budget guard; durable jobs and authenticated phone worker with documented Termux setup.
3. Operator review and private asset lifecycle; verified identity/quality evaluation.
4. Commerce/cohort imports, TikTok experiment preparation, virtual-model opportunity management, DM drafting.
5. Provision approved Azure environment, pair actual phone, perform live canary generation and one complete reviewed commercial loop.
6. Enable each permitted external action separately after connector and account validation.

Acceptance tests cover independent proposal layering, aggregated critiques, invalid schema/citation rejection, timeouts and budget exhaustion, no unauthorized provider fallback, RAG access isolation and deletion, prompt injection, duplicate jobs/messages/payments, phone offline recovery, SSE errors, scoped uploads, disclosure/offer grounding, opt-out, cost accounting and retention.
Offline tests do not prove Azure deployment, device compatibility or platform integration. Report mocked versus live checks separately.

## Current blockers for live operation
No Azure account/credit balance, model deployments, device pairing, canonical reference assets, distribution/commerce credentials or inbox connector have been verified. Implementation may proceed after architecture review, but provisioning, live generation and messaging cannot be represented as complete without these.

## References checked
https://ld.chino.icu/features/http-api
https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/multiple-agent-workflow-automation
https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content
