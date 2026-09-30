# Azure + S24 Ultra MoA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a tested Azure-only reasoning system, S24 Local Dream worker, editable RAG, and measured commercial workflows.
**Architecture:** Explicit Python three-layer MoA with centrally mediated actions. Azure supplies reasoning, durable orchestration and private storage; the S24 generates images. Build the core first, then independently test device/cloud, operator, and commercial components.
**Tech Stack:** Python 3.11+, unittest, SQLite FTS5 for development, Azure Functions/Storage/identity SDKs, Termux and Local Dream HTTP/SSE.
**Spec:** ../specs/2026-09-30-azure-localdream-moa-design.md (approved September 30, 2026).

## Global Constraints
- No third-party inference fallback.
- At least two independent proposers plus critic and aggregator are required for a successful MoA run.
- Limit each run to three layers, explicit token limits, bounded timeout and retries.
- No recursively spawning agents.
- Apply tenant/persona/access/expiry filters BEFORE ranking.
- Start in dry-run.
- Offline tests do not prove Azure deployment, device compatibility or platform integration.
- Preserve existing local commands and stored experiments; keep secrets and private assets outside git.
- Production hosting, reasoning and storage use Azure; image generation uses Local Dream on S24 exclusively.
- Live spending requires verified credit eligibility and owner-configured ceiling. Unknown eligibility disables live operation.

## Review Focus
- Cross-customer or expired knowledge must never leak through retrieval (Tasks 1, 10).
- Network fragmentation, app shutdown and lease loss must not duplicate generation/delivery (Tasks 4, 5).
- Concurrent workers must not overspend or double claim (Tasks 3, 6).
- Changed assets/offers must invalidate stale approvals and grounded replies (Tasks 7, 10).
- Gross receipts, payouts and immature retention cohorts must not inflate measured profit (Task 8).

## File and dependency map
Each task below owns focused modules and tests. Task 1 -> 2 -> 3 forms the reasoning core; Task 4 -> 5 -> 6 forms the durable device path; 7 binds approved assets; 8 measures results; 9 and 10 consume RAG/MoA/action interfaces; 11 joins all paths; 12 verifies real accounts/device. No task activates outbound messaging or paid provisioning implicitly.

---

### Task 1: RAG document lifecycle
**Files:** Create: `spicecore/knowledge.py`. Tests: `tests/test_knowledge.py`. Modify: `spicecore/cli.py`.
**Interfaces:** KnowledgeStore.add(document: dict) -> str; revise(document_id: str, document: dict) -> str; archive(document_id: str) -> None; delete(document_id: str) -> None; search(query: str, scope: dict, limit: int = 8) -> list[dict].
**Consumes:** Approved spec and existing Store connection conventions.
- [ ] Write failing unittest cases: test_scope_before_limit: another customer cannot retrieve private memory even if it ranks highest; test_delete_removes_all_text: deleted phrase is absent from source and FTS; test_expiry_and_revision: archived/expired and superseded chunks are excluded.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_knowledge.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Use SQLite FTS5 and immutable revisions with heading chunks; require owner, rights, source, namespace, sensitivity, evidence class, persona and expiry. Apply scope before ranking. Delete source/chunks/vectors, retain only non-sensitive audit IDs. Add CLI knowledge add/revise/search/archive/delete.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: rag document lifecycle`; exclude secrets, local databases, references and generated assets.

### Task 2: Three-layer Mixture of Agents
**Files:** Create: `spicecore/moa.py`. Tests: `tests/test_moa.py`.
**Interfaces:** async run_moa(task: dict, evidence: list[dict], client: ModelClient, budget: BudgetLedger) -> dict; ModelClient.complete(role: str, messages: list[dict], limits: dict) -> dict.
**Consumes:** Task 1 retrieval results.
- [ ] Write failing unittest cases: test_layers: proposals do not see sibling outputs, critics see all proposals, aggregator sees critiques; test_bad_citation: invented evidence fails; test_timeout: incomplete run yields no actionable result; test_injection: retrieved instruction cannot expand allowed actions.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_moa.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Select applicable independent research/creative/commerce/persona calls, then critics receiving every proposal, then aggregator. Require at least two proposers, one critic and aggregator. Validate JSON fields, cited chunk IDs and allowed action requests. Persist deployment/usage/latency and outputs, not hidden reasoning. Retrieved content is data only.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: three-layer mixture of agents`; exclude secrets, local databases, references and generated assets.

### Task 3: Azure configuration and budget enforcement
**Files:** Create: `spicecore/azure_models.py`, `spicecore/budget.py`, `config/runtime.example.json`. Tests: `tests/test_azure_models.py`, `tests/test_budget.py`.
**Interfaces:** BudgetLedger.reserve(run_id: str, maximum_cents: int) -> str; settle(reservation_id: str, actual_cents: int) -> None; AzureModelClient.complete(role: str, messages: list[dict], limits: dict) -> dict.
**Consumes:** Task 2 ModelClient/BudgetLedger protocols.
- [ ] Write failing unittest cases: test_concurrent_reservations: total cannot exceed cap; test_credit_expired: zero live calls; test_nonazure_endpoint: rejected before network; test_failed_call: incurred usage remains charged and unused reservation releases; test_unknown_cost: no inference without bounded cost.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_azure_models.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Persist atomic reservations and actual charges in SQLite development. Configure approved Azure HTTPS endpoints/deployments, API versions, region, credit eligibility evidence/expiry and owner caps. Use Azure identity; pin supported Azure SDK dependencies in requirements.txt. Reject redirects/hosts outside approved Azure configuration; no external fallback. Set default three layers, 30-second call timeout, two attempts and per-call max output 1024 tokens; cost estimate must include every possible attempt. Owner supplies daily spend ceiling before live calls.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: azure configuration and budget enforcement`; exclude secrets, local databases, references and generated assets.

### Task 4: Durable job lifecycle and action gate
**Files:** Create: `spicecore/jobs.py`, `spicecore/actions.py`. Tests: `tests/test_jobs.py`, `tests/test_actions.py`.
**Interfaces:** JobStore.enqueue(kind: str, payload: dict, key: str) -> str; claim(worker_id: str, now: str) -> dict | None; renew(job_id: str, lease_token: str) -> None; complete(job_id: str, lease_token: str, result: dict) -> dict; ActionGate.authorize(request: dict) -> dict.
**Consumes:** Task 3 persistent budgets and runtime configuration.
- [ ] Write failing unittest cases: test_duplicate_key_conflict: same key/different payload rejected; test_late_completion: reconcile hashed artifact without duplicate delivery; test_stop: blocks queued external actions; test_unapproved_asset: cannot publish; test_agent_permissions: inferred permission cannot authorize.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_jobs.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Implement SQLite job backend for development and interfaces for Azure queues. One image lease per device, 120-second renewable lease, heartbeat every 30 seconds, maximum three claims then dead-letter. Idempotency compares payload hashes. Default dry-run, centrally mediated actions, account scopes, daily quotas, approval/version checks, pause and emergency stop; specialists receive no execution tools.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: durable job lifecycle and action gate`; exclude secrets, local databases, references and generated assets.

### Task 5: Local Dream phone worker
**Files:** Create: `spicecore/localdream.py`, `spicecore/phone_worker.py`, `scripts/setup-phone.sh`, `docs/phone-worker.md`. Tests: `tests/test_localdream.py`, `tests/test_phone_worker.py`.
**Interfaces:** LocalDreamClient.generate(settings: dict) -> dict; PhoneWorker.tick(device_state: dict) -> dict.
**Consumes:** Task 4 leased jobs and completion contract.
- [ ] Write failing unittest cases: test_fragmented_sse: split network chunks assemble final image; test_json_error: no success artifact; test_bad_image_and_limit: reject invalid/oversized output; test_offline: defer with no cloud inference; test_lease_loss: checkpoint reconciles without regeneration.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_localdream.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Termux polls authenticated Azure API outbound, calls only http://127.0.0.1:8081/generate, parses SSE and JSON errors, validates PNG/JPEG signature and limits output to 32 MiB. Retain job-ID completion checkpoint before upload. Serial generation; defer below 25% battery unless charging or at thermal severity >=3; unknown device state defers. Validate actual installed API/model capabilities; model loading remains manual. No invented health endpoint or unsupported LoRA feature. Record seed, model, source hash and latency.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: local dream phone worker`; exclude secrets, local databases, references and generated assets.

### Task 6: Azure control plane and private assets
**Files:** Create: `azure/function_app.py`, `azure/host.json`, `infra/main.bicep`, `spicecore/cloud_storage.py`, `docs/azure-runbook.md`. Tests: `tests/test_control_plane.py`, `tests/test_cloud_storage.py`.
**Interfaces:** CloudJobAPI.claim(device_id: str) -> dict | None; renew(job_id: str, lease_token: str) -> None; complete(job_id: str, lease_token: str, artifact: dict) -> dict; AssetStore.put(job_id: str, content: bytes) -> dict; signed_upload(job_id: str) -> dict.
**Consumes:** Tasks 3–5 transport, leases and device contracts.
- [ ] Write failing unittest cases: test_unauthenticated: HTTP 401 and no lease; test_wrong_worker: HTTP 403; test_signed_scope: upload cannot target another job; test_etag_conflict: retry cannot overspend/double lease; test_expired_credit_preflight: no resource creation.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_control_plane.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Azure Functions, Storage queues/Blob, Key Vault, managed identities and restricted device authentication. Use a durable database strategy with atomic claims/reservations; SQLite is never shared across Functions. Azure Table ETag conditional writes can implement job/budget metadata; Blob holds versioned evidence and append events. Provisioning validates subscription/credit evidence/region and owner caps first. SAS uploads expire after 10 minutes, scoped to exact blob; no public assets. Protect completion against cross-device job theft. Credit/capacity unverified means disabled deployment command.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: azure control plane and private assets`; exclude secrets, local databases, references and generated assets.

### Task 7: Authenticated operator review and identity validation
**Files:** Create: `spicecore/operator.py`, `spicecore/identity_checks.py`. Tests: `tests/test_operator.py`, `tests/test_identity_checks.py`.
**Interfaces:** IdentityCheck.record(persona_id: str, reference_version: str, reviewer: str, selections: list[bool], drift: list[str]) -> dict; OperatorService.decide(candidate_id: str, reviewer: str, decision: str) -> dict.
**Consumes:** Tasks 1, 4, 6 evidence, assets and action receipts.
- [ ] Write failing unittest cases: test_replaced_artifact: prior approval invalidated; test_threshold: 8/10 fails, two 9/10 passes only without recurring drift; test_auth: review endpoint requires identity; test_rollback: published historical receipt not rewritten.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_operator.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Keep existing loopback web.py for local use. Add authenticated Azure operator endpoints and mobile view for evidence, jobs, spend, review, pause, stop and rollback of unpublished work. Approvals bind artifact hash and persona/reference version. Celeste needs two reviewers each >=9/10 and no recurring drift; store prompts and rejected outputs. Never infer a pass from img2img.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: authenticated operator review and identity validation`; exclude secrets, local databases, references and generated assets.

### Task 8: Commerce and cohort evidence
**Files:** Create: `spicecore/commerce.py`, `spicecore/experiments.py`. Tests: `tests/test_commerce.py`, `tests/test_experiments.py`.
**Interfaces:** CommerceLedger.import_event(event: dict) -> dict; cohort_report(as_of: str) -> list[dict]; ExperimentPolicy.recommend(arms: list[dict], seed: int) -> dict.
**Consumes:** Existing Store event IDs and Task 3 cost records.
- [ ] Write failing unittest cases: test_duplicate_payment: idempotent; test_profit: 2500 gross -500 fee -500 other costs =1500 contribution; test_payout: payout is not additional sales; test_currency: mixed currencies separated; test_delayed_window: open windows cannot become winners; test_retention: denominator excludes immature cohorts.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_commerce.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Add gross, fees, chargebacks/refunds, inference, rejected production, storage, distribution, labor and separate settled payouts. Migrate existing ledger without interpreting old gross as net. Currency is explicit and reports never sum different currencies. Track pseudonymous cohorts, renewal and repeat purchases, attribution method/window. Comparable arms with closed outcome windows and randomized bounded exploration; clicks cannot create profit. Promote evidence with sample size and uncertainty labels.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: commerce and cohort evidence`; exclude secrets, local databases, references and generated assets.

### Task 9: TikTok content and modeling workflows
**Files:** Create: `spicecore/content.py`, `spicecore/modeling.py`. Tests: `tests/test_content.py`, `tests/test_modeling.py`.
**Interfaces:** ContentService.prepare(persona_id: str, pillars: list[str], count: int) -> list[dict]; ModelingPipeline.transition(lead_id: str, next_state: str, evidence: dict) -> dict.
**Consumes:** Tasks 1, 2, 4, 7, 8 knowledge, proposals, approvals and measurements.
- [ ] Write failing unittest cases: test_missing_disclosure: cannot approve; test_no_reward_claim: eligibility unknown reported explicitly; test_unsupported_lead: cannot qualify without synthetic acceptance; test_contract: approval mandatory; test_physical_modeling: reject promise of attendance.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_content.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Prepare three persona pillars, hook variants, original scripts/storyboards/captions, AI labeling and campaign attribution. Limit batch count to configured cap. Add deterministic video assembly interface for phone assets; no generative-video fallback. Model media kit and leads through discovered/qualified/drafted/owner-approved/sent/negotiating/contracted/fulfilled/paid. Require synthetic-model acceptance, rights, deliverables, territories, term, exclusivity, revisions, deposit/balance. External outreach and contracts remain reviewed.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: tiktok content and modeling workflows`; exclude secrets, local databases, references and generated assets.

### Task 10: Grounded DM drafting and privacy
**Files:** Create: `spicecore/dms.py`. Tests: `tests/test_dms.py`.
**Interfaces:** DMService.ingest(message: dict) -> dict; draft(message_id: str) -> dict; opt_out(conversation_id: str) -> None; authorize_reply(draft_id: str, policy: dict) -> dict.
**Consumes:** Tasks 1, 2, 4 approved offers, MoA and action gate.
- [ ] Write failing unittest cases: test_cross_customer_memory: cannot retrieve; test_opt_out: suppress even queued reply; test_price_expired: abstain/escalate; test_duplicate_message: one draft; test_unverified_connector: no outbound send; test_dm_injection: cannot invoke tools.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_dms.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Authenticated inbound interface, private per-recipient RAG scope, duplicate suppression, cooldown and opt-out. Voice is witty, selective and luxury-minded; disclose fictional identity and ground offers in approved current facts. Default draft-only. Escalate uncertain age, disputes, sensitive requests, bespoke commitments, unsupported facts. No false availability/exclusivity, fabricated emergencies, guilt or vulnerability targeting. No live connector is fabricated.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: grounded dm drafting and privacy`; exclude secrets, local databases, references and generated assets.

### Task 11: Runnable integration and documentation
**Files:** Create: `spicecore/cli.py`, `README.md`, `.github/workflows/ci.yml`, `tests/test_end_to_end.py`. Tests: `tests/test_end_to_end.py`.
**Interfaces:** CLI commands: knowledge, moa, worker, jobs, campaign, modeling, dm, commerce, operator; dry-run demo fixture -> structured report.
**Consumes:** Earlier task interfaces and approved spec.
- [ ] Write failing unittest cases: test_complete_loop: evidence IDs connect every stage; test_no_credentials: live mode fails visibly; test_existing_suite: all previous tests pass; test_demo_labels: never reports live Azure/device/publishing success.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_end_to_end.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Wire services with explicit config and shared task/experiment IDs. Add isolated temp-database demo: retrieve canon/offer, run fake Azure MoA, lease job, simulate Local Dream artifact, approve, prepare post, import sale/renewal, compute contribution and draft grounded DM. CI runs unittest on Python 3.11+ with no credentials. Report fixture/mock status on every demo; production never selects fake client automatically.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: runnable integration and documentation`; exclude secrets, local databases, references and generated assets.

### Task 12: Live canary and controlled rollout
**Files:** Create: `docs/live-acceptance.md`, `docs/operations.md`. Tests: `tests/test_live_preflight.py`.
**Interfaces:** preflight(config: dict, receipts: dict) -> dict; rollout action policy -> versioned receipt.
**Consumes:** Earlier task interfaces and approved spec.
- [ ] Write failing unittest cases: test_missing_receipt: preflight reports blocked; test_connector_permission: action cannot enable from offline test; test_rollout_version: stale policy denied; test_credit_expiry: pending paid calls halted.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_live_preflight.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: After real Azure credit/account access, device pairing and canonical references are available, run bounded Azure inference, phone generation, private upload, mobile review and one reviewed commercial loop. Verify actual fees, identity and connector permissions. Record live receipts separately from offline tests. Enable permitted publishing and replies per account/action only after explicit configuration and successful live test. Test restore/deletion and emergency stop. If accounts or phone are absent, mark live checks blocked, ship implementation PR with that limitation rather than claiming production readiness.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: live canary and controlled rollout`; exclude secrets, local databases, references and generated assets.

## Execution and completion
Recommend native execution in this session because the core contracts are tightly coupled and deterministic tests permit economical incremental verification. A fresh whole-branch reviewer follows implementation.
Create an implementation branch based on the approved design branch; do not deploy or claim live readiness from mocked tests. Deliver a PR with implemented versus blocked live checks, exact test results and operational setup instructions.
Owner reviews this plan and selects native or subagent-driven execution before product code begins, as required by the planning skill.
