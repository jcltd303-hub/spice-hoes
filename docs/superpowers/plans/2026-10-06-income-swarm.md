# Income swarm implementation plan

> **For agentic workers:** Use parallel agents for the independent queue, platform, analytics, and commerce tasks; the primary agent connects the runtime and verifies the combined result.

**Goal:** Run a bounded generation -> release -> publication -> verified outcome -> learning loop without repeated CLI intervention.

**Architecture:** Reuse SQLite, CoreAutopilot, ExperimentPlanner, and LearningController. Persist publication and runtime state beside the ledger. Resume actual provider operations and independently ingest signed commerce events.

**Tech stack:** Python 3.11+, stdlib SQLite/HTTP, existing Go/QNN media runtime, official social and Stripe APIs.

**Spec:** `docs/superpowers/specs/2026-10-06-income-swarm-design.md`

## Global constraints

- Production model compute stays on configured local llama.cpp endpoints and S24 Go/QNN.
- No fictional revenue, fabricated post URLs, leaked credentials, or customer PII.
- Owner controls budget and auto-release configuration; models cannot modify them.
- No live posting or spending without working configured accounts and offer.

## Review focus

1. A process stops after a remote submit but before saving a receipt: hold, never blindly resubmit.
2. A payment or cumulative metric arrives twice: unchanged earnings/exposure.
3. A provider fails midway through generation: preserve consumed budget and prevent immediate repeat storms.
4. The runtime restarts or runs concurrently: cadence, queue, receipts, and locks persist.
5. The model returns unsupported copy or missing quality evidence: hold release.

### Task 1: Durable queue

Own scheduler and worker. Preserve existing MediaJob scheduling; add `schedule_candidate`, persistent claims, provider state, backoff, receipt-first reconciliation. Write and run failing regression tests, implement, run scheduler/worker suites.

### Task 2: Actual platform delivery

Own platform adapters and PublishResult. Pending result contract is `response_metadata={"pending": true, "provider_state": {...}}`; resume using `resume_metadata`. Fix real image/video submissions and confirmed permalinks. Verify official API docs. Write and run failing HTTP-boundary tests, implement, run adapter suites.

### Task 3: Accurate exposure

Own analytics modules and count handling in planner results. Persist per-stream high-water marks; ingest deltas atomically, reject conflicts, honor aggregate event counts. Write and run failing cumulative snapshot tests, implement, run analytics/learning suites.

### Task 4: Verified commerce

Add `StripeCommerce(store, signing_secret, live_mode=True)`, `ingest(raw_body, signature_header)`, `retry_pending()`, `status()` and an HTTP webhook handler. Verify raw signatures; deduplicate payments/refunds; isolate test mode. Write failing authenticated transaction tests, implement, run commerce suites.

### Task 5: Unattended runtime

Add swarm config/runtime with `status()` and `tick()`, persisted cadence and budget reservations, owner-authorized scored release, tracked offers, publisher/metrics/commerce/settlement orchestration. Add CLI commands, operator bridge actions, a supervisor installer, and concise launch docs. Write runtime tests first; prove missing inputs block cleanly, restart/cost limits, scoped publication, and learning closure.

### Task 6: Combined verification and delivery

Run the entire Python suite, Go tests, and Node build. Review the combined diff with a fresh agent. Fix important findings with regression tests. Commit and push a feature branch, create a PR, inspect CI, and report implementation proof separately from the still-unconfigured live requirements.
