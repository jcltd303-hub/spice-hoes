### Task 6: Azure control plane and private assets
**Files:** Create: `azure/function_app.py`, `azure/host.json`, `infra/main.bicep`, `spicecore/cloud_storage.py`, `docs/azure-runbook.md`. Tests: `tests/test_control_plane.py`, `tests/test_cloud_storage.py`.
**Interfaces:** CloudJobAPI.claim(device_id: str) -> dict | None; renew(job_id: str, lease_token: str) -> None; complete(job_id: str, lease_token: str, artifact: dict) -> dict; AssetStore.put(job_id: str, content: bytes) -> dict; signed_upload(job_id: str) -> dict.
**Consumes:** Tasks 3–5 transport, leases and device contracts.
- [ ] Write failing unittest cases: test_unauthenticated: HTTP 401 and no lease; test_wrong_worker: HTTP 403; test_signed_scope: upload cannot target another job; test_etag_conflict: retry cannot overspend/double lease; test_expired_credit_preflight: no resource creation.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_control_plane.py' -v`; verify new cases fail for the missing behavior, not unrelated setup.
- [ ] Implement the interfaces in the owned files: Azure Functions, Storage queues/Blob, Key Vault, managed identities and restricted device authentication. Use a durable database strategy with atomic claims/reservations; SQLite is never shared across Functions. Azure Table ETag conditional writes can implement job/budget metadata; Blob holds versioned evidence and append events. Provisioning validates subscription/credit evidence/region and owner caps first. SAS uploads expire after 10 minutes, scoped to exact blob; no public assets. Protect completion against cross-device job theft. Credit/capacity unverified means disabled deployment command.
- [ ] Run each owned test file via unittest discovery; expect all cases PASS. Run `python3 -m unittest discover -s tests -v` before committing.
- [ ] Commit owned modules, tests and documentation with message `feat: azure control plane and private assets`; exclude secrets, local databases, references and generated assets.

