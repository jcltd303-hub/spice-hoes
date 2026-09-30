# Local Dream phone worker

Local Dream's official [HTTP API reference](https://ld.chino.icu/features/http-api) was checked on 2026-09-30. Load a model manually in the app before running Termux. This client calls only loopback POST /generate. There is no health/version probe or remote model startup.

The documented completion payload contains **raw RGB**, not PNG/JPEG. The client bounds stream/base64/decoded bytes to 32 MiB, checks positive dimensions, channels=3 and exact byte count, and writes a PNG with a validated signature. Progress previews consume the stream limit: keep previews disabled. Invalid JSON, HTTP errors, SSE errors and truncated streams never produce successful artifacts.

Before enabling generation, record an owner-verified installed app version, loaded model and allowed request fields as capabilities:
```python
capabilities = {'validated': True, 'version': 'OWNER-VERIFIED-VERSION',
                'model': 'OWNER-VERIFIED-LOADED-MODEL', 'fields': ['prompt', 'seed']}
```
This is a manual receipt, not discovery. Add fields only after a bounded canary confirms the installed model accepts them. Pin an explicit seed for reproducibility. Do not assume LoRA, face references or automatic model loading. Model-specific resolution/scheduler capabilities must be checked in the installed app.

PhoneWorker takes an injected authenticated outbound cloud adapter, LocalDreamClient, private checkpoint directory, and paired worker/device IDs. It starts in dry-run. The adapter must use owner-configured Azure HTTPS routes and authentication, scope upload URLs privately, fence every claim/renew/completion by worker/device/token, and implement:
- claim(worker_id, ISO8601_now, device_id=...) -> fenced image lease or None
- renew(job_id, lease_token)
- upload(job, encoded_image_bytes, result) -> serializable private upload receipt
- complete(job_id, lease_token, result) -> status=completed acknowledgment
- reconcile_artifact(job_id, historical_lease_token, result) -> durable artifact checkpoint

No routes are guessed here. Task6 supplies actual transport. The adapter must bound request timeouts and provide private upload association by job ID/hash. An authenticated=True marker is an injection contract; it does not implement authentication itself. Never pass a local JobStore as a production cloud adapter.

Call tick with current online:boolean, battery:0..100, charging:boolean and Android thermal_severity:int. Missing/unknown values defer. Below 25% battery defers unless charging; thermal severity >=3 always defers. Collect thermal status with a device-supported Android API; Termux battery telemetry alone is insufficient. There is no inference fallback.

One process/file lock per device in the same checkpoint directory serializes work. Use one paired worker and one directory on the phone; the cloud lease also enforces device serialization. A background heartbeat renews every 30 seconds while generation runs. Lost lease does not cancel an in-progress backend request: its result is durably checkpointed and reconciled without regeneration.

PNG bytes and job-ID metadata are fsynced before upload; SHA256, seed, model/version, source-image hash and latency accompany completion. Upload/completion retries preserve the exact result payload. After lease loss, or any failed delivery, the checkpoint is retained and the worker reports reconciliation_pending. Historical JobStore reconciliation records an artifact without delivering or changing ownership. Until Task6 provides authenticated finalization/operator recovery, such checkpoints can block new work and are never silently treated as completed. Do not delete them to force regeneration.

Run setup-phone.sh in Termux, install and authorize Termux:API separately if using its telemetry. Disable battery optimization for Termux only after assessing battery/thermal behavior; keep Local Dream on the phone and port8081 off public networks. Inject the real cloud adapter into your application runner and call tick on a bounded polling schedule; setup does not invent a production runner or transport.

Offline unittest/CI evidence validates parser and lifecycle fixtures only. Actual S24 compatibility, installed model behavior, Android telemetry, Azure pairing, credentials, upload scopes and live generation remain owner live checks.
