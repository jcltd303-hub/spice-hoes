# S24 local GPU/NPU and offline voice

The phone runs the controller, MoA planning, evidence retrieval, image generation, identity checks, offline speech, FFmpeg assembly, and publishing queue. Larger video/lip-sync jobs use an attended free GPU notebook. No hosted model or storage subscription is required by the default configuration.

| Work | Local execution path |
| --- | --- |
| Planning, campaign copy, engagement drafts | llama.cpp GGUF on Adreno OpenCL; Vulkan or experimental Hexagon selectable |
| Still images | Existing standalone QNN HTP model packs or stable-diffusion.cpp Vulkan |
| Face detection and embeddings | Existing compiled SCRFD/ArcFace QNN artifacts |
| Speech output | Updated Android companion with offline TextToSpeech voices |
| Spoken conversation | On-device SpeechRecognizer → local model → offline Android playback |
| Video, lip sync, large-model training | Finite Colab/Kaggle GPU jobs; unavailable GPUs stay pending |

## Termux setup

```bash
cd ~/spice-hoes
git fetch origin
git switch main
git pull --ff-only
bash scripts/setup-s24-local.sh
```

Use your installed GGUF, or download a small model explicitly. A practical starting point is the official Qwen2.5 1.5B Instruct Q4_K_M model; start small while diffusion and the controller share phone RAM.

```bash
SPICE_LLM_MODEL_URL='https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf' \
  bash scripts/setup-s24-local.sh
bash scripts/start-local-llm.sh
```

The launcher prints devices before accelerated startup, prefers OpenCL, then Hexagon, then Vulkan, binds `127.0.0.1:8083`, uses a 4096-token context, and limits the server to one concurrent sequence. `SPICE_LLM_BACKEND` selects `auto`, `cpu`, `opencl`, `vulkan`, or `hexagon`. `SPICE_LLM_DEVICE` can select an exact device name; clear it when changing backend. Exported launcher settings override `.env.swarm` and `.env.s24`. Use a second Termux session for the controller. Missing requested acceleration stops with a driver/backend instruction instead of silently selecting another backend. `SPICE_LLM_BACKEND=cpu`, `SPICE_LLM_DEVICE=none`, or `SPICE_LLM_GPU_LAYERS=0` disables all offload and skips device probing. A reported service being ready does not establish tokens per second or the percentage of operations offloaded.

## Recovering from the Adreno Q4_K Vulkan crash

`mul_mat_vec_q4_k_f32_f32: vk::Device::createComputePipeline: ErrorUnknown` means Vulkan failed to compile a compute pipeline. Listing `Vulkan0: Adreno 750` only proves device enumeration. Upstream reports describe Qualcomm driver failures for this shader; they do not establish the exact driver version on your phone. The tokenizer warning about `</s>` is a separate message. Do not use `--n-gpu-layers 0` alone as CPU recovery: llama.cpp can still offload other operations unless the device and operation/KV offload are disabled.

Start your existing model on CPU:

```bash
SPICE_LLM_BACKEND=cpu bash scripts/start-local-llm.sh
```

This passes `--device none --n-gpu-layers 0 --no-kv-offload --no-op-offload`. It does not enumerate GPU/NPU devices. To use the Adreno GPU through OpenCL instead, stop the CPU server with Ctrl-C, then:

```bash
pkg update
pkg install -y llama-cpp llama-cpp-backend-opencl
SPICE_LLM_BIN="$(command -v llama-server)" SPICE_LLM_DEVICE= \
  SPICE_LLM_BACKEND=opencl SPICE_LLM_GPU_LAYERS=99 \
  bash scripts/start-local-llm.sh
```

The launcher selects the reported `GPUOpenCL...` device and requests offload. The pinned Snapdragon build also includes OpenCL and can be selected by omitting `SPICE_LLM_BIN`. Upstream OpenCL documentation lists Adreno 750 and Q4_K/Q6_K support, so this path can use an existing Q4_K_M GGUF without converting it. A particular ROM, model architecture, or vendor driver may still fail; verify the startup log and a real model response. The first OpenCL startup compiles kernels and can take longer. The launcher keeps a manually selected Termux binary separate from the Snapdragon artifact's libraries.

### OpenCL backend loads but reports no platform

`ggml_opencl: platform IDs not available` comes from `clGetPlatformIDs`, before GGUF loading or kernel compilation. Installing the llama.cpp backend does not establish that the Android driver can initialize in Termux. The Termux maintainer describes `opencl-vendor-driver` as not supporting Adreno in [this investigation](https://github.com/termux/termux-packages/issues/27640). Some Qualcomm versions use a loader `libOpenCL.so` that opens a separate `libOpenCL_adreno.so` at runtime; copying declared dependencies alone can miss it. Reports for Adreno 830 describe copying both libraries. That is evidence for a recovery attempt, not proof of success on every S24 ROM.

The project includes an isolated setup using the libraries already installed on your phone:

```bash
bash scripts/setup-adreno-opencl.sh && \
  SPICE_LLM_BIN="$(command -v llama-server)" SPICE_LLM_DEVICE= \
  SPICE_LLM_BACKEND=opencl SPICE_LLM_GPU_LAYERS=99 \
  bash scripts/start-local-llm.sh
```

It copies the vendor entry point and available Adreno implementation/helper libraries into ignored `runtime/adreno-opencl/` releases. It leaves Termux's package-managed loader and the system libraries intact. A fresh child process probes the actual OpenCL API, prints platform/GPU/driver names or an exact error, and times out after 30 seconds. Only a successful GPU enumeration activates a release; a failed attempt keeps the earlier installation. The launcher uses its library path only for OpenCL/auto selection, checks hashes against the phone's original files, and stops with a setup instruction if an Android update changed them. CPU mode bypasses this installation entirely.

The JSON `ready` flag describes GPU enumeration, not tested kernels or model inference. `stage: load-library` includes the linker's missing library/symbol error. `stage: platforms` with `code: -1001` means the driver still cannot enumerate a platform. `stage: gpu-devices` means no usable GPU was found or its information query failed. Timeout/signal exit statuses point to a driver hang/crash. Preserve that output before trying more backend changes. A model download or quantization change cannot repair a failed platform-enumeration call.

To compare the unmodified vendor entry point directly:

```bash
LD_LIBRARY_PATH="/vendor/lib64:/vendor/lib64/egl:$PREFIX/lib:/system/lib64" \
  timeout 30s python3 scripts/probe-opencl.py --library /vendor/lib64/libOpenCL.so
```

Run `setup-adreno-opencl.sh` again after a ROM update. It refreshes an isolated release only if the new driver enumerates a GPU. If enumeration remains unavailable, keep the local model running with `SPICE_LLM_BACKEND=cpu` and use the printed driver error for the next diagnosis.

In a second Termux session, verify the model independently of the other local services:

```bash
curl -fsS http://127.0.0.1:8083/health
curl -fsS http://127.0.0.1:8083/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"spice-local","messages":[{"role":"user","content":"Say hello in one short sentence."}],"max_tokens":32}'
bash scripts/s24-doctor.sh
```

Sources: [Qualcomm Q4_K Vulkan pipeline failure](https://github.com/ggml-org/llama.cpp/issues/28635), [S24 Vulkan compatibility investigation and remaining Q4_K limitations](https://github.com/ggml-org/llama.cpp/pull/29165), [pinned OpenCL support](https://github.com/ggml-org/llama.cpp/blob/08246a28f6000100433d297c4e037c02e9d2d464/docs/backend/OPENCL.md), and [Termux vendor driver packaging](https://github.com/termux/termux-packages/tree/master/packages/opencl-vendor-driver). The upstream Vulkan investigation is still experimental; this project does not apply that unmerged patch or claim phone hardware validation.

## Controller planning checks

```bash
set -a
source .env.swarm
set +a
python3 -m spicecore.cli --json compute-status
python3 -m spicecore.cli --json moa --objective 'Plan one measurable content experiment using approved project facts'
```

All production planning entry points, including the web control plane, use this local selector. An external OpenAI-compatible endpoint is available only when `SPICE_TEXT_PROVIDER=openai-compatible`, `MOA_BASE_URL`, and `MOA_MODEL` are explicitly configured. The local adapter never sends model lists to a router or uses cloud fallbacks.

## Experimental Hexagon LLM backend

Upstream llama.cpp supports a Snapdragon Hexagon backend, but it needs its Android/Hexagon toolchain and runtime libraries. The optional `Build S24 Snapdragon LLM` workflow builds a pinned upstream revision with the vendor toolchain and packages v75 libraries for the S24.

```bash
pkg install gh
gh auth login
# The published branch starts the native build automatically. Inspect it:
gh run list -R jcltd303-hub/spice-hoes --branch main
# After Build S24 Snapdragon LLM succeeds:
bash scripts/install-llama-snapdragon-termux.sh
SPICE_LLM_DEVICE=HTP0 SPICE_LLM_MODEL="$HOME/models/compatible-q4_0.gguf" \
  bash scripts/start-local-llm.sh
```

Use the exact `HTP...` name printed by `--list-devices`. Quantization/operator compatibility differs from Vulkan; use a supported model (upstream examples use Q4_0/Q8_0) and confirm offload in the startup log. The optional cross-build passed GitHub CI; actual phone offload and hardware throughput still require device verification. Set `SPICE_LLM_BUILD_RUN` to a successful run ID if a newer main-branch build is still pending. Existing QNN diffusion and face embedding remain the established NPU lane.

## Android voice companion

Install the updated `spice-identity-debug-apk` artifact from the `Android Identity APK` workflow, open the app, and install an offline voice in Android's speech settings. Tap **Copy voice pairing command** in the companion and paste the command into Termux. Save that `SPICE_ANDROID_VOICE_TOKEN` in the private `.env.swarm` for later sessions. Mutating voice requests require this bearer token. For microphone turns, tap the app's microphone permission control and keep its activity visible. The companion uses `createOnDeviceSpeechRecognizer`; absent on-device recognition produces an unavailable response, never a cloud substitution.

```bash
curl -fsS http://127.0.0.1:8082/voice/health
curl -fsS -H "Authorization: Bearer $SPICE_ANDROID_VOICE_TOKEN" http://127.0.0.1:8082/voice/voices
# Open the companion in split-screen alongside Termux for microphone access.
python3 -m spicecore.cli --json voice-chat --persona zara_voss --turns 5
```

`SPICE_ANDROID_VOICE_MAP` maps persona IDs to the offline voice names returned by `/voice/voices`. Profile pitch/pace applies to rendered speech and conversation playback. Local speech synthesis also plugs into the existing media pipeline with `SPICE_VOICE_PROVIDER=android`. Piper remains available on hosts where its native runtime is installed. These are device speech APIs; they do not claim a GPU/NPU delegate, voice cloning, full-duplex streaming, or guaranteed latency. The companion's existing mock identity-transfer backend remains clearly marked mock; real identity work runs through the existing Go/QNN tools.

## Attended media batches

The default environment selects `SPICE_VIDEO_PROVIDER=freegpu` and `SPICE_LIPSYNC_PROVIDER=freegpu`. Rendering exports every missing scene job into `data/freegpu/jobs/` before synthesizing speech. The render remains retryable with an explicit waiting message. Run each ZIP in [the notebook](free-gpu-media.md), copy the returned result ZIPs into `data/freegpu/results/`, and render the same job again. Results must match the original job and input hashes. The default FP16 SVD-XT job uses the approved image and motion settings; text is a descriptor, not text guidance. Local FFmpeg retimes clips to the scene plan. After local assembly, lip sync can export its own finite job; repeat the same result-copy step. The saved speech and base video are reused on retries so their hashes stay stable. Technical QA and human review still run before publication.

For an already available desktop GPU, the existing ComfyUI/MuseTalk adapters remain selectable. The Colab path uses the notebook's upload/run/download flow; it does not provide an always-on service. A free GPU allocation can end or be unavailable, so interactive phone conversation uses local speech/model services.

## Public media without a storage provider

Social platforms still need HTTPS access to still images. Set `SPICE_MEDIA_PUBLIC_BASE_URL` to your own HTTPS media host and `SPICE_MEDIA_PUBLIC_DIR` to the matching directory. A loopback server is included:

```bash
python3 -m spicecore.media_delivery --directory data/public-media --port 8788
# In another session, optionally expose only this read-only media server:
cloudflared tunnel --url http://127.0.0.1:8788
```

Set the returned HTTPS hostname as `SPICE_MEDIA_PUBLIC_BASE_URL` in `.env.swarm`, keeping the tunnel alive until platform fetches complete. For unattended publishing use a persistent HTTPS host. The server exposes only content-addressed JPEGs, rejects directory listing/traversal/symlinks, and strips private EXIF before delivery. The adapter fetches the public file and compares its bytes before handing its URL to the publisher. Platform access tokens, offer configuration, and signed payment receipts remain required for production income.
