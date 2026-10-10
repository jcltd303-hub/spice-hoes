# S24 Local Compute Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the core migration and superpowers:dispatching-parallel-agents for the independent Android and notebook deliverables. Track the steps below.

**Goal:** Replace hosted dependencies with local S24 planning/media/voice and an attended free GPU batch path.

**Architecture:** The Python controller calls local llama.cpp and existing Go QNN/Vulkan engines. The Android companion supplies offline speech. Exported job bundles cross the phone/notebook boundary without an always-on hosted service.

**Tech Stack:** Python stdlib/Pillow, Go, Android Kotlin speech APIs, llama.cpp Vulkan, existing QNN runtimes, Colab/PyTorch/Diffusers.

**Spec:** `docs/superpowers/specs/2026-10-08-s24-local-compute-design.md`

## Global Constraints

- No retired hosted-provider dependencies or automatic paid-provider fallback.
- Preserve verified income/knowledge, review, identity, and publishing gates.
- Loopback defaults; local recognition never silently uses cloud speech.
- Actual readiness determines acceleration availability.
- Colab is attended, finite batch execution; no uptime promise or account workarounds.

## Review Focus

- Missing local models or a stopped service must produce actionable blockers.
- One phone model cannot sustain four parallel MoA requests without a memory limit.
- Public media must not expose EXIF, source filenames, credentials, or arbitrary files.
- Native microphone usage requires foreground UI and granted permission.
- Notebook bundles must reject traversal, mismatched jobs, and altered artifacts.

### Task 1: Core migration and local launchers

**Files:** `spicecore/local_compute.py`, `spicecore/moa.py`, `spicecore/swarm_factory.py`, `spicecore/media_delivery.py`, `spicecore/swarm.py`, `config/swarm.env.example`, `scripts/install-income-swarm-termux.sh`, new S24 setup/start/doctor scripts, corresponding tests and active docs.

**Interfaces:** `LocalChatProvider` follows `OpenAICompatibleChatProvider`; `PublicDirectoryMediaDelivery.prepare(candidate) -> str`, `readiness() -> dict`; `compute_status() -> dict` returns installed/probed services.

- [x] Write regression tests for local role routing, serialized calls, verified memory, delivery integrity and invalid configuration.
- [x] Run the tests and confirm missing/new behavior fails.
- [x] Implement the local provider, public media server/delivery, factory and launchers; remove obsolete adapter and references.
- [x] Run targeted tests, then the complete Python suite and shell checks.

### Task 2: Android offline voice companion

**Files:** confined to `android/identity-service/**`; parent integrates the Python client/CLI.

**Interfaces:** `GET /voice/health`, `GET /voice/voices`, `POST /voice/synthesize` accepts text/voice/language/pitch/pace and returns WAV base64, `POST /voice/speak` plays offline speech, `POST /voice/listen` returns on-device recognized text.

- [x] Add router validation and availability tests before implementation.
- [x] Implement offline Android speech behind injectable transport/backend interfaces, main-thread dispatch and bounded operation times.
- [x] Add microphone permission/UI controls and document foreground requirements.
- [x] Verify JVM/Android checks available in this environment.

### Task 3: Free GPU batch bridge

**Files:** `spicecore/freegpu.py`, `scripts/freegpu-worker.py`, `notebooks/spice_free_gpu_media.ipynb`, `tests/test_freegpu.py`, `docs/free-gpu-media.md`; parent integrates CLI commands.

**Interfaces:** Export/import CLI via `python -m spicecore.freegpu`, versioned ZIP manifest, worker executes explicitly selected video/tts/transcribe/lipsync jobs and returns hash-verified artifacts.

- [x] Test bundle round trip, invalid input, traversal and result mismatches before implementation.
- [x] Implement safe export/import and a real attended worker with configurable model weights and zero service charge reporting.
- [x] Provide Colab cells for GPU check, dependency install, upload, execution and result download; no public server/tunnel.
- [x] Run unit tests and syntax-check worker/notebook code.

### Task 4: Integration and release verification

- [x] Connect native voice to Python media rendering and an interactive local CLI.
- [x] Add machine-readable local compute diagnostics and copy/paste Termux instructions.
- [x] Run Python, Go and web checks; inspect removal scan and branch diff.
- [ ] Complete publication after independent review and release CI. The review findings are fixed; commit, PR and deployment are the final release steps.

## Execution record

The user's migration request authorizes implementation, and the earlier request to publish to Vercel authorizes the release. Work proceeded in an isolated checkout with independent Android and notebook tasks. The review identified voice pairing, portrait video bounds, keyless CLI routing and local readiness authentication gaps; all four were fixed with regressions. No external cloud account resources were deleted.

Release verification: 378 Python tests, 62 Android JVM tests, Go tests and both binaries, and the web build passed. Shell and notebook syntax were checked. GitHub CI also built the final paired APK. Local UI/API smoke checks verified HTML delivery, compute status and browser origin restrictions. The existing optional static Space workflow's invalid secret condition was fixed, and actionlint validates all changed workflows. Final CI checks the APK signature/lint and the optional native LLM toolchain. S24 hardware throughput and actual CUDA inference require the phone and an attended GPU session; desktop checks do not establish them.
