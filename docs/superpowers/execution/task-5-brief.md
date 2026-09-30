# Task 5: Local Dream phone worker
**Files:** Create: `spicecore/localdream.py`, `spicecore/phone_worker.py`, `scripts/setup-phone.sh`, `docs/phone-worker.md`. Tests: `tests/test_localdream.py`, `tests/test_phone_worker.py`.
**Interfaces:** LocalDreamClient.generate(settings: dict) -> dict; PhoneWorker.tick(device_state: dict) -> dict.
**Consumes:** Task 4 leased jobs and completion contract.
- [ ] Write failing unittest cases: test_fragmented_sse: split network chunks assemble final image; test_json_error: no success artifact; test_bad_image_and_limit: reject invalid/oversized output; test_offline: defer with no cloud inference; test_lease_loss: checkpoint reconciles without regeneration.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_localdream.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Termux polls authenticated Azure API outbound, calls only http://127.0.0.1:8081/generate, parses SSE and JSON errors, validates PNG/JPEG signature and limits output to 32 MiB. Retain job-ID completion checkpoint before upload. Serial generation; defer below 25% battery unless charging or at thermal severity >=3; unknown device state defers. Validate actual installed API/model capabilities; model loading remains manual. No invented health endpoint or unsupported LoRA feature. Record seed, model, source hash and latency.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: local dream phone worker`; exclude secrets, local databases, references and generated assets.

