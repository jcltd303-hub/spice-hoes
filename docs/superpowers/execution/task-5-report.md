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

## Fix round1: streamed response deadline and meaningful size regressions
Reviewer Important: read(65536) could internally keep filling its buffer from a trickle stream beyond the generation deadline. Minor: old100-byte limit fixture did not exceed the actual stream cap.

Changed spicecore/localdream.py to use HTTPResponse.read1, which returns after an available transport read, set each underlying socket timeout to the remaining overall budget, and check the clock immediately after the read. Removed unnecessary error-body reading. No background reader survives the request/lease. The injected fake response exposes read1 and set_read_timeout; the production urllib HTTPResponse socket receives the remaining deadline.

Changed tests/test_localdream.py with a real http.client.HTTPResponse on an io.BufferedReader over a controlled RawIOBase/socket. Each trickle read advances a deterministic clock; the test asserts deadline within1.2 simulated seconds and socket timeout constraints. Actual stream overflow is65545bytes against cap65544; a valid6-byte RGB completion under4-byte cap separately checks decoded byte rejection.

RED: root TEST-only head5ec68062d4b7693f22a1b7532b3628c4c24867f7, Actions run36751222718.
Command: python3 -m unittest discover -s tests -v.
Exact relevant result:78 tests, sole FAIL test_httpresponse_trickle_respects_deadline; AssertionError:6553.6 not <=1.2.
This demonstrates the old buffering read consumed6553.6 simulated seconds before another deadline check.

GREEN: source head36f7ecb004148aef9168cdcad8b6e51fc2afee90, Actions run36751338315 success.
Command: python3 -m unittest discover -s tests -v.
Exact result: Ran78 tests in1.811s; OK.
No unnecessary suite rerun after this verified fix.

Self-review: checked read1 path, remaining-budget socket timeout, closure in finally, explicit limit error assertions and preservation of existing fragmented SSE behavior. Earlier report socket-read deadline limitation is corrected for streamed response reads. urllib connection/response-header handling still uses configured connection timeout; no live networking/device claim is made.

## Fix round2: interrupt buffered HTTP chunk framing
Rereviewer found round1 incomplete: HTTPResponse.read1 still calls buffered readline for chunk headers/extensions and trailers. A trickling framing line can exceed the total response-body budget even when individual socket operations do not time out.

Changes: spicecore/localdream.py starts a remaining-budget watchdog holding the actual response socket. At expiry it marks the deadline and calls socket.shutdown(SHUT_RDWR), interrupting buffered framing and body reads. It performs no background reads. Every success/error path cancels and joins the watchdog before closing the response; deadline-caused transport/parser exceptions become TimeoutError. The existing read1 and remaining-budget per-read timeout remain.

Regression: tests/test_localdream.py test_chunked_socket_trickle_deadline constructs an actual socket.socketpair and HTTPResponse with Transfer-Encoding:chunked. A peer thread sends one valid chunk extension one byte every10ms for400ms, while client budget is80ms. It asserts TimeoutError under250ms, response closure and no surviving watchdog or peer thread. Peer cleanup is bounded and joined.

RED: TEST-only head9681eecff6d1169fe3576db996bb2389f17b6b52, Actions run36752061996.
Command: python3 -m unittest discover -s tests -v.
Exact relevant result:79tests,1failure, test_chunked_socket_trickle_deadline elapsed0.403 >0.25.
This confirms the pre-fix implementation remained blocked inside buffered chunk framing.

GREEN: source head428112c7f4b3b74a9f4c3e45312b106662d3029e, Actions run36752203425 success.
Command: python3 -m unittest discover -s tests -v.
Exact result: Ran79tests in1.622s; OK.
No repeated full suite after verification.

Self-review: verified real socket shutdown releases buffered parser, timed error normalization, cancellation/join cleanup, and preservation of prior nonchunked deterministic regression and image bounds.

Explicit limitation: the hard cancellation deadline applies after urllib returns the response, including all response-body chunk framing/trailers. Connection and initial response-header parsing use the configured urllib socket timeout; adversarial trickled initial headers are not protected by a separate total-request watchdog. This does not claim a hard whole-request deadline. The controller accepted keeping this wave scoped to the original response-read/chunk-framing finding. Actual trusted loopback Local Dream behavior and S24 networking remain live validation.
