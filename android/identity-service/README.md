# Spice Identity (Android)

Loopback inference companion for the `spice-hoes` pipeline. Full spec: `spice_identity_android_apk_spec.md`.

**Status: Phase A + B.** Visible status UI, `127.0.0.1:8082`, `/health`, and `/transfer` image transport with
validation, hashing, queueing, thermal reporting, crash handler and rotating log. The backend is
`MockIdentityBackend` (target passthrough): it reports `backend:"mock"`, `accelerated:false`,
`identity_applied:false`. **No identity is transferred yet.** Phase C needs a commercially licensed
identity model (spec section 13) plugged in behind `IdentityBackend`.

**Offline voice is implemented separately from identity.** Native Android TextToSpeech selects only
installed voices that do not require a network connection. Speech recognition uses only
`SpeechRecognizer.createOnDeviceSpeechRecognizer` on API 31+; a missing on-device engine or language
model is a blocker, with no cloud fallback. Android manages the engines' execution: this app does
not claim to enable or verify S24 GPU/NPU speech acceleration. Identity continues to report the
mock backend accurately.

## Build

CI (`.github/workflows/android-identity.yml`) builds `spice-identity-debug-apk`. Locally:
`cd android/identity-service && gradle assembleDebug testDebugUnitTest lintDebug`
(Gradle 8.9+, a full JDK 17, Android SDK platform 35 and build tools). Set `ANDROID_HOME` to the SDK.
The debug APK is `app/build/outputs/apk/debug/app-debug.apk`.

JVM tests inject `VoiceBackend` into the router and `SpeechPlatform`/`VoiceDispatcher` into the
offline backend, plus `VoiceAuthorizer` and a token store for pairing tests. They exercise caller
authorization, private token persistence, JSON media types, permission/foreground/service gates, offline-only
selection, WAV validation/cleanup, single-operation admission, timeouts, late callbacks and shutdown.
Actual device audio, installed language models, latency and hardware acceleration need device tests.

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

## Offline voice from Termux

1. Open Spice Identity. In Android text-to-speech settings, enable an engine with downloaded offline
   voice data. Restart the companion after changing/installing its voice data.
2. Tap **Copy voice pairing command** in the visible app, then paste the copied
   `export SPICE_ANDROID_VOICE_TOKEN='hex-token'` command into Termux. The app generates 32 bytes with
   `SecureRandom`, encodes them as 64 lowercase hex characters, and saves the token in private
   `SharedPreferences` using `MODE_PRIVATE`. It persists across service/app restarts. Clearing app data
   or reinstalling requires pairing again. The token is never logged, returned over HTTP, or copied
   automatically; only this explicit native UI tap exports it. Android 13+ clipboard previews mark
   this command as sensitive. Keep the copied command/token private.
3. To use recognition, tap **Grant microphone access** and accept Android's permission dialog. The
   app never requests microphone permission automatically. Android 12/API 31+ and an installed
   on-device recognizer/language model are required. Availability can differ between phones and engines.
4. Keep Spice Identity visible **and resumed** while calling `/voice/listen`, for example in
   split-screen with Termux. Switching away cancels active listening. A foreground service notification
   alone does not authorize microphone capture. TTS does not require microphone access or visible UI.

```bash
curl -s http://127.0.0.1:8082/voice/health
curl -s http://127.0.0.1:8082/voice/voices \
  -H "Authorization: Bearer $SPICE_ANDROID_VOICE_TOKEN"
curl -s http://127.0.0.1:8082/voice/speak \
  -H "Authorization: Bearer $SPICE_ANDROID_VOICE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"text":"Hello from offline Android speech","language":"en-US"}'
curl -s http://127.0.0.1:8082/voice/listen \
  -H "Authorization: Bearer $SPICE_ANDROID_VOICE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"language":"en-US","timeout_seconds":15}'
```

| Endpoint | Contract |
|---|---|
| `GET /voice/health` | Read-only, no authentication required. Reports `auth_required:true`, `ready`, `tts_ready`, `recognition_available`, `tts_reason`, `recognition_reasons`, combined `reasons`, permission/UI/SDK diagnostics. `ready` means at least one speech capability is available; it is independent of `/health` and mock identity. |
| `GET /voice/voices` | `{voices:[{voice_id,name,language,offline:true}],provider:"android-offline",cost_cents:0}`. Installed offline voices only. |
| `POST /voice/synthesize` | JSON `{text,voice_id?,language?,pitch?,pace?}` → `{audio_base64,mime_type:"audio/wav",provider:"android-offline",cost_cents:0}` after synthesis finishes. |
| `POST /voice/speak` | Same fields → `{spoken:true,provider:"android-offline",cost_cents:0}` after playback finishes. |
| `POST /voice/listen` | `{language?,timeout_seconds?}` → `{text,provider:"android-on-device",cost_cents:0}` for one utterance, after recognition finishes. |

Every voice endpoint except `/voice/health` requires `Authorization: Bearer <paired-token>`;
query parameters, cookies and JSON token fields are not credentials. Token comparison uses
`MessageDigest.isEqual` on fixed-length ASCII values. Missing/malformed/incorrect credentials return
`UNAUTHORIZED`/401 with a Bearer challenge before any speech backend access. There is no HTTP token
creation, discovery or pairing endpoint. Authorized voice POST requests must use
`Content-Type: application/json` (optional parameters such as `charset=utf-8` are accepted);
missing or other media types return `UNSUPPORTED_MEDIA_TYPE`/415 before body parsing/backend access.
Pairing adds caller authorization to the existing microphone grant and resumed-activity requirements.

Use a `voice_id` from `/voice/voices`. `language` is a BCP-47 tag such as `en-US`; a bare tag such as
`en` can select a matching installed regional voice. Explicit regional tags and voice/language pairs
must match an offline voice. Text is nonblank and at most 4000 characters (or the engine's smaller
limit). Pitch/pace default to `1.0`, accept numeric `0.5`–`2.0`, and reset for each request.
Listening defaults to 15 seconds, accepts numeric 1–30 seconds, and never restarts continuously.
JSON voice bodies are limited to 32 KiB; synthesized WAV output is limited to 8 MiB.

Initialization has a 15-second deadline; TTS/playback has a 60-second deadline. Only one speech
operation runs at a time, including initialization; overlapping calls return `SERVER_BUSY`/503.
Completion and cancellation run on the main thread; HTTP workers wait with a deadline. Timeouts,
interruption, loss of UI visibility and service shutdown cancel work; stale callbacks cannot complete
a later request. Temporary WAV files are deleted after success or failure.

Failures retain the existing error envelope. Missing offline voices return `VOICE_UNAVAILABLE`/503;
unavailable on-device recognition returns `RECOGNITION_UNAVAILABLE`/503; missing microphone permission
returns `MICROPHONE_PERMISSION_REQUIRED`/403; hidden/paused UI returns `ACTIVITY_NOT_VISIBLE`/409;
deadlines return `VOICE_TIMEOUT`/504; engine/audio failures return `VOICE_FAILED`/500. Check
`/voice/health` for actionable reasons. It reports `accelerated:false` because GPU/NPU use is unverified.

Platform references: [TextToSpeech](https://developer.android.com/reference/android/speech/tts/TextToSpeech),
[Voice](https://developer.android.com/reference/android/speech/tts/Voice),
[SpeechRecognizer](https://developer.android.com/reference/android/speech/SpeechRecognizer).

## Layout

| Layer | Package |
|---|---|
| HTTP transport | `http/` |
| API / validation / metrics | `api/` |
| Image decode + limits | `image/` |
| Model/runtime | `backend/` (`IdentityBackend`) |
| Offline speech / bounded callbacks | `voice/` (`VoiceBackend`, `SpeechPlatform`, `VoiceOperations`) |
| Diagnostics | `DiagLog`, `CrashReporter`, `SpiceRuntime.statusText()` |
