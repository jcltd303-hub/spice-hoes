# Run the income loop

The swarm now connects MoA/RAG planning, S24 image production, scored release, persistent publishing, real post confirmation, social exposure, signed commerce, and learning. It runs bounded ticks, survives restarts, and reserves operating budget before model calls. The default launch lane is Instagram images; TikTok and YouTube accept compatible approved videos.

## Configure once

1. Copy `config/swarm.env.example` to `.env.swarm` and `config/swarm.example.json` to `data/swarm.json`. Keep these files private. Load your existing `.env.spicemedia` too.
2. Configure an Azure model endpoint, deployment, and key; the S24 `spicemedia` binary and QNN models; separate Azure Blob upload and read-only container SAS; the Instagram access token; and a Stripe webhook secret. The swarm never falls back to OpenRouter or another paid model provider.
3. Register the actual product offer with `offer-create`, then set its returned ID, HTTPS checkout destination, and the five persona/account mappings in `data/swarm.json`. Instagram mappings must use numeric account IDs. An offer name or estimated payout alone does not enable income. Create a deliverable product and configure fulfillment at checkout before selling it.
4. Set conservative batch reservations covering all Azure expert, aggregator, planner, and production costs. The example's values are operating estimates, not cloud prices. `policy-set` controls the daily ceiling; `monthly_budget_cents` controls the monthly ceiling. Failed calls retain reservations. Provider spend controls should use the same approved ceiling.
5. Choose `auto_approve: true` to authorize scored automatic release. Identity and quality must pass the owner's active thresholds and copy must pass validation. Otherwise content waits for the existing review desk. The model cannot change this setting.

For Stripe Payment Links, the swarm includes its tracking token as `client_reference_id`; the receiver reads it from the signed Checkout Session. `spice_ref` remains in other tracked links. Affiliate networks require their own authenticated commission reporting; a click is never a confirmed commission.

```bash
python3 -m spicecore.cli --json swarm-status --config data/swarm.json
./scripts/run-income-swarm.sh --once
./scripts/run-income-swarm.sh
```

The launcher loads private environment files. Direct Python commands require those variables to be exported already. The worker emits one JSON record per tick. `generation_enabled: false` pauses production while publication, metrics, commerce retry, and learning continue. The process handles termination signals and prevents two runtimes from operating the same local ledger concurrently.

## Payments

Run the signed receiver on the trusted backend hosting the ledger:

```bash
python3 -m spicecore.cli commerce-serve --host 127.0.0.1 --port 8766
```

Expose `/webhooks/stripe` through the backend's HTTPS ingress, and subscribe the merchant's Stripe webhook to Checkout payment, refund, dispute, balance fee, and payout events supported by `StripeCommerce`. Use the endpoint's own signing secret. There is no unauthenticated route that creates revenue. The receiver validates raw-body signatures and stores recoverable unmatched events without customer contact/payment details.

Only signed live paid transactions enter production earnings. Test transactions, manual imports, demo simulations, upload initiation, clicks, expected payouts, and incomplete provider responses stay separate. Known fees, refunds, chargebacks, and fee credits flow into contribution and learning; missing fees and cash payout evidence remain explicit in `verified_commerce`. Operating contribution includes recorded costs for content that never sold or was rejected. `campaign_contribution` scopes those costs to this campaign and separately shows conservative generation reservations, including failed attempts. Unknown expenses prevent these fields from claiming complete net profit.

## Unattended services

On the S24 in Termux, run `scripts/install-income-swarm-termux.sh`, configure the private files, inspect a single tick, and enable `spice-income-swarm` with `sv-enable`. The installer leaves the service stopped until configuration is complete; runit restarts it after process failures. Android must permit Termux background operation for the device to continue producing.

On Azure/Linux, supervise `scripts/run-income-swarm.sh` with the host's service manager and run the webhook receiver behind HTTPS on the same persistent ledger. The SQLite database and media directories must live on persistent storage. Do not put the loop or local media generation in a stateless function or a GitHub Actions job.

## Inspect and recover

`swarm-status` reports exact missing settings, queue counts, conservative reservations, and verified commerce. Scheduled, pending, confirmed, failed, and reconciliation states remain distinct. Retries use bounded backoff. A crash during an uncertain remote submission holds the job for reconciliation; confirm its provider receipt before retrying. This is intentionally separate from polling a known provider operation.

New production pauses when the review queue, unsettled batch limit, cadence, daily ceiling, or monthly ceiling is reached. Learning waits for confirmed publication timestamps, exposure, and the configured observation window. Set `learning_exposure_metric` to `views` (default) or `impressions`; the existing `min_impressions_to_learn` policy number applies to the explicitly selected counter. Rejected variants close as recorded negative cost evidence. Later refunds/fees/chargebacks amend the same replay experience and supersede earlier RAG summaries atomically. The next recommendation reports supporting published counts, uncertainty, and what changes its ranking. Deep RL remains gated on sufficient production evidence; historical unverified replay and snapshots stay outside that scope.

The implementation's offline tests do not establish a live business outcome. A complete live milestone needs a generated asset, a verified public post, a successful buyer payment and fulfillment, recorded costs/refunds, and a subsequent evidence-based decision. Positive income is measured from those receipts.

Azure MoA retrieves experiment summaries only when they belong to a current verified learning closure and production replay episode. Older manual/simulation results remain available in the general evidence desk, while approved product and persona facts continue to inform production planning.
