# Attended free GPU media jobs

Export one finite job on the phone, run it while present in the Colab notebook,
download the result, and import against the original job. This bridge does not
host an API. It never starts a public server, tunnel, keepalive, background
capacity polling, account workaround, or paid-provider fallback. GPU capacity
and session duration are not guaranteed. Unavailable compute or weights return
`pending` with a blocker and no artifacts; invalid media/inference errors return
`failed`. Both report `cost_cents: 0` for service charges. This does not account
for your device, electricity, connectivity, or independently selected hosting.

Batch upload/download cannot provide real-time voice or live video. Use the
phone's local native offline voice for live conversation, or an ephemeral
worker endpoint you explicitly supply and operate. A downloaded clip is still
subject to the existing identity, quality, review and publishing gates.

## Export on Termux

The controller requires only Python's standard library. Run in your checkout;
no PyTorch, CUDA or model weights need to be installed on the phone. Keep the
original ZIP for import. Use explicit local filenames, never a URL or directory.
Only files passed as arguments enter the bundle; the exporter does not scan a
persona directory or include credentials, repository files or model caches.

```bash
pkg install python
cd ~/spice-hoes
mkdir -p data/freegpu/jobs

# Small text-to-video model. Options are bounded, validated JSON.
python -m spicecore.freegpu export --task video \
  --prompt 'A fictional adult character walks through a sunlit garden, cinematic motion' \
  --model zai-org/CogVideoX-2b \
  --options '{"frames":17,"steps":20,"fps":8,"timeout_seconds":1800}' \
  --output data/freegpu/jobs/garden.zip

python -m spicecore.freegpu export --task tts \
  --text 'Welcome to the garden.' \
  --options '{"speaker_id":0,"length_scale":1.0}' \
  --output data/freegpu/jobs/welcome.zip

python -m spicecore.freegpu export --task transcribe \
  --audio /absolute/path/to/recording.wav --model small \
  --options '{"language":"en","max_seconds":300}' \
  --output data/freegpu/jobs/transcribe.zip

python -m spicecore.freegpu export --task lipsync \
  --video /absolute/path/to/approved-fictional-persona.mp4 \
  --audio /absolute/path/to/selected-speech.wav \
  --approved-fictional-persona \
  --options '{"fps":25,"max_seconds":30}' \
  --output data/freegpu/jobs/lipsync.zip
```

For the common free T4 image-to-video path, explicitly select `svd-i2v` and pass
an approved fictional-persona image. It uses FP16 SVD-XT, model CPU offload,
UNet forward chunking, and `decode_chunk_size=2`. Its default profile is
1024×576, 25 frames, 25 steps, 7fps, `motion_bucket_id=127` and
`noise_aug_strength=0.02`. `frames` accepts only 14 or 25. The model is
**image/motion conditioned: it does not follow the text prompt**. `prompt`
is retained in the manifest as a scene descriptor and is never passed to SVD.

```bash
python -m spicecore.freegpu export --task video \
  --prompt 'Fictional adult portrait scene; descriptor only' \
  --pipeline svd-i2v --model stabilityai/stable-video-diffusion-img2vid-xt \
  --image /absolute/path/to/approved-fictional-persona.png \
  --approved-fictional-persona --output data/freegpu/jobs/persona-motion.zip
```

This implements the [official Diffusers SVD low-memory example](https://huggingface.co/docs/diffusers/v0.35.1/en/using-diffusers/svd).
The [SVD-XT model card](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt)
documents its conditioning and limitations. The checkpoint's
[license source](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/blob/main/LICENSE.md)
is the Stability AI Community License; commercial use has its own terms.
No license workflow or paid service is added by this bridge.

CogVideoX-2b remains the standalone module's default text-to-video checkpoint;
it cannot preserve an image reference. CogVideoX-5b I2V remains an explicit,
heavier BF16 alternative. This worker returns pending on a T4 without native
BF16 support; more host RAM may be needed.

```bash
python -m spicecore.freegpu export --task video \
  --prompt 'The fictional adult character smiles and turns toward the camera' \
  --pipeline cogvideox-i2v --model zai-org/CogVideoX-5b-I2V \
  --image /absolute/path/to/approved-fictional-persona.png \
  --approved-fictional-persona --output data/freegpu/jobs/persona-cog5b-motion.zip
```

The approval flag records the caller's explicit approval of those supplied
fictional-persona assets. It does not infer consent or verify someone's identity.
TTS selects a generic open-weights voice; it performs no voice cloning.

If Android shared storage is needed, grant Termux storage access and copy the
exported ZIP to Downloads. Export/import in Termux's private checkout is the
recommended path. Bundle creation also supports filesystems without hardlinks.

```bash
termux-setup-storage
cp data/freegpu/jobs/garden.zip ~/storage/downloads/spice-garden-job.zip
```

## Run in Colab or your own ephemeral CUDA worker

Open `notebooks/spice_free_gpu_media.ipynb` in Colab, select a free GPU runtime,
and run the cells while attended. The notebook checks actual CUDA availability,
clones your trusted checkout/revision **or uploads the two checked worker source
files**, uploads/validates one job, installs task dependencies, executes once,
and downloads the result. Source upload works without publishing this branch.
Use your reviewed source; uploading Python files means executing that code.

The install cell preserves Colab's PyTorch and installs Diffusers 0.35.1 with
Transformers 4.x for video, Piper for TTS, or faster-whisper for transcription.
CUDA transcription needs CUDA 12 cuBLAS and cuDNN 9 discoverable before the worker
starts. The notebook adds their pip library directories to the child process's
`LD_LIBRARY_PATH`. Recreate or fix the runtime if dependencies are incompatible.
There is no hardware execution guarantee from a phone model name or Colab label.

The default video model is
[`zai-org/CogVideoX-2b`](https://huggingface.co/zai-org/CogVideoX-2b), formerly
`THUDM/CogVideoX-2b`. Its model card specifies FP16, 720×480, 49 frames at 8fps
for its six-second profile. We use a shorter 17-frame profile by default, with
sequential CPU offload, VAE slicing and tiling, and no initial `.to("cuda")`.
The model card describes low-memory offloading and explicitly cautions that its
memory measurements were not obtained on every GPU architecture. Shorter/fewer
steps may reduce quality. Model loading still consumes substantial host RAM and
download space. See the [model card](https://huggingface.co/zai-org/CogVideoX-2b)
and [Diffusers API](https://huggingface.co/docs/diffusers/v0.35.1/en/api/pipelines/cogvideox).

The worker checks at least 4 GiB free VRAM and 8 GiB available host RAM before
video loading. It caps PyTorch video allocations at 14 GiB or 95% of the GPU,
whichever is smaller. Sequential offload is slow and these thresholds are
guardrails, not measured peak guarantees. OOM, missing weights/dependencies,
inaccessible downloads, BF16 incompatibility, process death, or timeout produce
a blocker. No other model is substituted. `--min-free-gpu-gib`,
`--min-host-ram-gib` and `--max-gpu-gib` are explicit worker controls; the PyTorch
allocation cap does not constrain CTranslate2 or an external MuseTalk process.
Use `options.revision` to pin a video model's Hugging Face commit for reproducible
weights; the default is `main`. Custom model IDs must be compatible with the
selected pipeline and its bounded profile. SVD custom checkpoints also need
the `fp16` weight variant. SVD never falls back to CogVideoX or a hosted API.

On an already configured worker:

```bash
python scripts/freegpu-worker.py garden.zip --output garden-result.zip

# Explicitly select and install open voice weights, including their model card.
python -m pip install 'piper-tts>=1.3,<2'
python -m piper.download_voices en_US-lessac-medium --data-dir /tmp/spice-voices
python scripts/freegpu-worker.py welcome.zip --output welcome-result.zip \
  --piper-model /tmp/spice-voices/en_US-lessac-medium.onnx

python scripts/freegpu-worker.py transcribe.zip --output transcript-result.zip
```

Piper runs local CPU inference with its adjacent `.onnx.json` configuration.
An independently installed executable can be selected with `--piper-bin`;
otherwise the worker uses `python -m piper`. The worker validates nonempty,
nontruncated PCM WAV output. It never generates placeholder speech.
See the [official Piper CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md)
and each voice's license/model card.

Transcription uses `faster_whisper.WhisperModel(..., device="cuda")`,
`int8_float16` by default, one worker, and a fully consumed segment iterator.
Input is duration-checked and normalized locally using file-only FFmpeg
protocols before inference. The JSON transcript includes actual segments,
language and duration; no-speech input truthfully returns an empty transcript.
See [faster-whisper requirements](https://github.com/SYSTRAN/faster-whisper#gpu).

For lip sync, install [MuseTalk 1.5](https://github.com/TMElyralab/MuseTalk) and
its documented weights yourself, preferably in its own compatible environment.
This includes `models/musetalkV15/{unet.pth,musetalk.json}`, SD VAE, Whisper,
face parsing, DWPose and face-detection weights. The bridge does not silently
download or replace that stack. Missing required weights return a blocker.

```bash
python scripts/freegpu-worker.py lipsync.zip --output lipsync-result.zip \
  --musetalk-dir /absolute/path/to/MuseTalk \
  --musetalk-python /absolute/path/to/musetalk-venv/bin/python
```

It writes a one-task inference YAML with normalized, generated local paths,
then executes this documented installed-weights command with an argument list:

```bash
python -m scripts.inference --inference_config <generated.yaml> \
  --result_dir <private-results> \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --version v15 --use_float16 --batch_size 1 --fps 25
```

The bridge requires an actual decodable video with audio at
`<private-results>/v15/lipsync.mp4`; it never copies the source clip as a claimed
lip-sync result. Standard video output is also probed and decoded with FFmpeg.
All inference runs in a supervised process group. The job timeout includes
downloads/loading/generation; on POSIX, all descendants are killed at expiry.
The supported attended GPU environment is Linux/Colab. Other platforms need
equivalent CUDA and process supervision and are not verified here.

## Import back on the phone

Copy the downloaded result to the checkout, then use the exact original job.

```bash
cp ~/storage/downloads/spice-attended-result.zip data/freegpu/garden-result.zip
python -m spicecore.freegpu import data/freegpu/garden-result.zip \
  --job data/freegpu/jobs/garden.zip --output-dir data/freegpu/results
```

The JSON result contains `job_id`, `task`, `status`, `cost_cents`, `artifact_paths`
(a list of absolute local filenames), `artifacts` (a map from artifact basename
to absolute local filename), and `blocker`. For example, video results expose
`artifacts["video.mp4"]`. Pending/failed results expose `artifact_paths: []` and
`artifacts: {}`. Completed files are placed under
`<output-dir>/<job_id>/artifacts/`. Pending/failed imports create no directories
or artifacts. Reimporting a completed job refuses to overwrite existing output.
Return code 0 means a valid bundle/result was handled: **inspect `status`**.
Malformed bundles or CLI arguments exit 2. Retry a pending job manually after
resolving its blocker, using a new result ZIP filename.

## Manifest v1 and limits

ZIPs contain only `manifest.json` and the files it lists. JSON object keys must
be unique. Export replaces source basenames with role names, for example
`inputs/image.png` or `inputs/audio.wav`; it stores no original absolute paths.

| Field | Job | Result |
| --- | --- | --- |
| `version` / `kind` | `1` / `job` | `1` / `result` |
| `job_id` / `task` | Generated UUID hex or explicit safe ID; one supported task | Must match the retained job |
| `inputs` / `options` | Explicit text/file references and fully populated finite options | Must exactly match the retained job |
| `approved_fictional_persona` | Boolean, required true for image/video assets | Must match the retained job |
| `files` | List of `{path,size,sha256}` for every input | Same shape for every actual artifact |
| `job_manifest_sha256` | Absent | SHA-256 of canonical original manifest, binding inputs/options/file hashes |
| `status` / `cost_cents` / `blocker` | Absent | `completed`, `pending` or `failed`; exactly `0`; null or actionable blocker |

Canonical manifest JSON uses UTF-8, sorted keys, no extra whitespace and no
NaN/Infinity. With an explicit `job_id`, identical inputs/options produce
identical job ZIP bytes; archive timestamps/modes are fixed and source mtimes
are omitted. Omit the ID for a newly generated UUID on each export. Results
with altered files, wrong IDs/tasks/source hashes,
unsupported versions, or nonzero service charges are rejected before import.
SHA-256 provides integrity checking, **not authentication**: someone who can
replace both a file and its declared hash can rewrite an unsigned result. Only
use results from your trusted attended worker; media validation is not a
sandbox for hostile source code or installed model stacks.

The maximum ZIP is bounded to 256 MiB payload plus manifest/ZIP overhead:
32 entries, 128 MiB per file, 256 MiB total file data, 64 KiB manifest,
64 KiB central directory, and at most 100:1 compression ratio. ZIP64,
multi-disk/encrypted/unsupported compression archives, directories, symlinks,
special files, duplicate or unlisted entries, absolute/traversal/backslash/
drive-letter paths are rejected. Local input/output path components may not be
symlinks. Hash verification precedes extraction, which uses a new private
directory and rejects existing destinations. Export uses stored ZIP entries;
already compressed media needs no additional archive compression.

| Task | Accepted finite options (defaults shown) | Required inputs/artifacts |
| --- | --- | --- |
| All | `timeout_seconds=1800`, integer 1..3600 | One job per bundle |
| Video T2V / optional Cog I2V | `pipeline=cogvideox-t2v`, `model=zai-org/CogVideoX-2b`, `revision=main`, `width=720`, `height=480`, `frames=17` (9..49, 4k+1), `steps=20` (1..50), `fps=8` (1..30), `seed=42`, `guidance_scale=6` (1..10). Explicit `cogvideox-i2v` selects 5B I2V by default | `prompt`, approved `image` required for Cog I2V; `video.mp4` |
| Video SVD I2V | `pipeline=svd-i2v`, `model=stabilityai/stable-video-diffusion-img2vid-xt`, `revision=main`, `width=1024`, `height=576`, `frames=25` (14 or 25), `steps=25` (1..50), `fps=7` (1..30), `seed=42`, `motion_bucket_id=127` (0..255), `noise_aug_strength=0.02` (0..1), `decode_chunk_size=2` (1..2) | Descriptor `prompt`, approved `image`; `video.mp4`. No text guidance |
| TTS | `speaker_id=0` (0..1000), `length_scale=1` (0.5..2) | `text` (1..4000 chars); `speech.wav` (≤600 seconds) |
| Transcribe | `model=small`, `language=null`, `compute_type=int8_float16` (or `float16`), `max_seconds=300` (1..600) | `audio`; `transcript.json`, optional nonempty `transcript.txt` |
| Lip sync | `fps=25` (1..30), `max_seconds=60` (1..60) | Approved `video`, selected `audio`; `lipsync.mp4` |

Unknown inputs/options, URL inputs, empty text/files, unbounded values and
noninteger count/time options fail validation. Prompts also have a 4000-character
limit. Worker commands/paths are selected only through attended worker arguments,
never through a ZIP manifest. Video/tts/transcribe/lipsync execution uses actual
installed open-weights inference and contains no production mock path.

Python integration (for the controller's own subcommands) can call
`export_job(output, task=..., inputs=..., options=...)`,
`read_bundle(path, kind="job")`, and
`import_result(result, job_bundle=original, output_dir=destination)` from
`spicecore.freegpu`. The standalone module CLI is complete independently of
`spicecore.cli`.

## Controller retries and notebook setup

For MediaPipeline jobs, retain the result ZIPs themselves in
`data/freegpu/results/` and retry the same media job. The controller validates
and imports them automatically. Every downloaded ZIP includes the source job ID
in its filename, so the three scene results do not overwrite one another.
Standalone export jobs use the explicit import command above.

For a selected lip-sync job with an assigned GPU, the notebook can run
`scripts/setup-musetalk-colab.py`. It clones pinned upstream MuseTalk 1.5, creates
a separate Python 3.10/PyTorch 2.0.1 CUDA 11.8 environment, installs MMLab wheel
dependencies and downloads only inference weights from their primary sources.
It leaves Colab's own PyTorch installation in place. An installed MuseTalk path
can be supplied instead. Setup and actual CUDA inference remain separate checks;
installation errors are blockers.

The worker accepts portrait or landscape 1080p inputs and normalizes face video
within 720×1280 while preserving aspect ratio. Image conditioning also preserves
aspect ratio with padding rather than stretching the source person's face.
Native offline speech is padded with silence when needed to retain the full
scene plan during lip sync. The controller performs final framing, captions and
real FFmpeg decoding before review. Captions are timing estimates rather than
word-aligned recognition output.
