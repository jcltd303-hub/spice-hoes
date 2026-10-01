# Spice Identity (Android)

Loopback inference companion for the `spice-hoes` pipeline. Full spec: `spice_identity_android_apk_spec.md`.

**Status: Phase A + B.** Visible status UI, `127.0.0.1:8082`, `/health`, and `/transfer` image transport with
validation, hashing, queueing, thermal reporting, crash handler and rotating log. The backend is
`MockIdentityBackend` (target passthrough): it reports `backend:"mock"`, `accelerated:false`,
`identity_applied:false`. **No identity is transferred yet.** Phase C needs a commercially licensed
identity model (spec section 13) plugged in behind `IdentityBackend`.

## Build

CI (`.github/workflows/android-identity.yml`) builds `spice-identity-debug-apk`. Locally:
`cd android/identity-service && gradle assembleDebug testDebugUnitTest` (Gradle 8.9+, JDK 17).

## Use from Termux

```bash
curl -s http://127.0.0.1:8082/health
```

```python
import base64, json, urllib.request

def b64(p): return base64.b64encode(open(p, "rb").read()).decode()

req = urllib.request.Request(
    "http://127.0.0.1:8082/transfer",
    data=json.dumps({"reference_image": b64("ref.png"), "target_image": b64("scene.png"),
                     "preserve_composition": True}).encode(),
    headers={"Content-Type": "application/json", "Accept": "image/png"},  # raw PNG back
)
resp = urllib.request.urlopen(req)
open("out.png", "wb").write(resp.read())
print(resp.headers["X-Output-Sha256"], resp.headers["X-Backend"], resp.headers["X-Identity-Applied"])
```

Omit the `Accept` header for JSON with `image_base64`, `sha256`, and `timings_ms`.
Errors are `{"error": {"code": "<ErrorCode>", "message": "...", "request_id": "..."}}`.

## Layout

| Layer | Package |
|---|---|
| HTTP transport | `http/` |
| API / validation / metrics | `api/` |
| Image decode + limits | `image/` |
| Model/runtime | `backend/` (`IdentityBackend`) |
| Diagnostics | `DiagLog`, `CrashReporter`, `SpiceRuntime.statusText()` |
