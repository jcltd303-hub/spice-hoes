# Task5 Local Dream phone worker implementation report

Status: DONE_WITH_CONCERNS pending actual S24/Azure integration. Shared local exec-server outage prevented local execution; authorized GitHub blob-only fallback used, root remained sole tree/commit/ref writer.

## Implemented
- LocalDreamClient calls loopback POST /generate, disables environment proxies and redirects, parses fragmented SSE incrementally, rejects JSON/HTTP/SSE errors and missing completion, bounds response/base64/RGB/output PNG.
- Official https://ld.chino.icu/features/http-api verified 2026-09-30: completion.image contains raw RGB (channels=3), not encoded PNG/JPEG. Strict dimensions/exact length checks precede stdlib PNG encoding and output signature/size validation. Positive installed version/model/allowed-field manual receipt required; no invented health endpoints, model loading, or LoRA support.
- PhoneWorker accepts an injected authenticated outbound Azure API contract, paired worker/device identities, dry-run by default, device-state readiness gates, per-device process lock, 30-second heartbeat.
- Lease loss never abandons a running generation; resulting image and job-ID metadata are fsynced before upload, hash checked on recovery, and reconciled historically without regeneration. Failed delivery retains reconciliation_pending. Completion payload remains stable across retries.
- Records seed, loaded model/version, source-image hash, artifact SHA256 and local latency.
- Termux runtime setup and operator documentation; actual transport deferred to Task6.

## TDD RED evidence
Root published TEST-only head 2bfcc8061c63c6702e5fc1bc10b6aa2399c4f3f7.
GitHub Actions run 36749961912 ran python3 -m unittest discover -s tests -v.
Exact relevant result: Ran 67 tests; FAILED (errors=2).
Missing spicecore.localdream and spicecore.phone_worker caused the two import errors; existing tests passed. Missing implementation was the expected RED cause.

## GREEN evidence
Source head 3fcf088cd73c87af4ef34c4dd1dabdc90aae870a.
GitHub Actions PR run 36750476135: success. Push run 36750469907: success.
Command: python3 -m unittest discover -s tests -v.
Exact result: Ran 77 tests in 1.649s; OK.
All 12 owned phone/parser tests pass alongside 65 existing tests. Full suite ran once before completion via authorized remote CI; no local runtime or device test is claimed.

## Files
spicecore/localdream.py; spicecore/phone_worker.py; tests/test_localdream.py; tests/test_phone_worker.py; scripts/setup-phone.sh; docs/phone-worker.md.

## Self-review
Read generated source and tests before publication. Fixed production loopback opener to reject redirects and ignore proxy environment. Changed worker default to dry-run and made live fixture tests opt in. Added actual cross-process file-lock check and a generation waiting on failed heartbeat to prove retained output/no upload on lost lease. Tests verify fragmented documented RGB SSE, invalid image/JSON/SSE, manual capability requirement, unsupported fields, unknown/offline/hot/low battery, durable checkpoint before upload, restart without regeneration, heartbeat loss and serial lock.

## Limits and concerns
Offline CI does not prove real S24 compatibility, installed model API, telemetry, Azure deployment/authentication, scoped upload or platform integration.
Task6 owns real authenticated routes and private upload association by job/hash; authenticated=True is an adapter injection assertion, not authentication machinery.
Historical reconciliation checkpoints without completion/ownership changes. Operator/Task6 finalization remains needed after lease loss; retained checkpoints can block new work safely.
Per-device local lock assumes a single checkpoint directory shared by all paired phone processes; cloud fencing must independently enforce device serialization.
Cloud adapter calls must configure bounded timeouts; a blocked renew call can delay shutdown. Local Dream read timeout bounds socket inactivity and stream deadline is checked between reads.
Manual capability receipt must be owner validated against installed app/model and bounded canary; version/model discovery is deliberately not guessed.
