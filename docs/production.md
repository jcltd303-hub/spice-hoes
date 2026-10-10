# Production deployment

## Media lanes

- Planning and conversational text: local llama.cpp on the S24, one sequence at a time.
- Image/identity: existing S24 QNN HTP and Vulkan runtime/model packs.
- Speech: Android offline TextToSpeech and on-device recognition.
- Video/lip sync: attended ZIP jobs in `notebooks/spice_free_gpu_media.ipynb`.
- Assembly, captions, technical QA and review: local Python/FFmpeg.

Start with [S24 setup](s24-local-runtime.md) and [free GPU media](free-gpu-media.md).
The default image-to-video batch uses FP16 SVD-XT with CPU offload for a common
free T4. SVD has no text prompt guidance; use the explicit CogVideoX BF16 option
on a compatible GPU when text-conditioned image motion is required. Generated
scenes are retimed locally to the scene plan. Exact speech and base-video bytes
are retained while lip sync is pending, including across controller restarts.
Returned lip sync is framed and captioned before FFmpeg decoding/metadata QA.
QA does not claim to measure black frames or audio clipping.

Existing ComfyUI, Piper and MuseTalk adapters remain selectable on machines with
those installed runtimes. See [self-hosted ComfyUI](comfyui-colab.md). There is
no automatic paid-provider fallback or placeholder render when compute fails.

## Supabase

`supabase/migrations/0001_production_archive.sql` creates private event and
media-asset archive tables plus a private `spice-private` Storage bucket. RLS is
enabled and no browser/client policies are granted. Use the secret/service-role
credential only from trusted backend workers.

Supabase Free is useful for launch/staging, but it can pause inactive projects and
does not include automatic backups. Keep the local SQLite backup routine active
until a paid durability tier or separate backup process is in place.

## Hosting

### Vercel

Use Vercel for the static/operator UI or lightweight HTTP edges. Do not run
Piper, MuseTalk, ComfyUI, or long video jobs in Vercel serverless functions.
The media workers remain local/Colab/container workers.

### Hugging Face Spaces

The repository includes a static Space target and a Dockerfile. Current free
static Spaces can host the dashboard, while compute/Docker availability depends
on the account plan and hardware allocation.

Set GitHub secret `HF_TOKEN` and repository variable `HF_SPACE_REPO` to enable
`.github/workflows/deploy-hf-static.yml`.

## Default runtime environment

```bash
SPICE_TEXT_PROVIDER=local
MOA_BASE_URL=http://127.0.0.1:8083/v1
MOA_MODEL=spice-local
SPICE_VIDEO_PROVIDER=freegpu
SPICE_FREEGPU_DIR=data/freegpu
SPICE_VOICE_PROVIDER=android
SPICE_ANDROID_VOICE_URL=http://127.0.0.1:8082
SPICE_LIPSYNC_PROVIDER=freegpu
SPICE_MEDIA_PUBLIC_DIR=data/public-media
SPICE_MEDIA_PUBLIC_BASE_URL=https://YOUR-MEDIA-HOST
```

Copy `.env.example` or `config/swarm.env.example` for all supported settings.
The optional private archive configuration is independent of the default public
media delivery. Only reviewed, sanitized assets enter the owner-hosted public
JPEG directory; private SQLite records and notebook inputs are not served.

For the operator UI on the phone, install Node.js in Termux and run `npm install`.
Load the private environment with `set -a; source .env.swarm; set +a`, then run
`npm run dev` and open `http://127.0.0.1:3000`. Vercel hosts the static UI.
Set `VITE_API_BASE_URL` at build time to an explicitly hosted HTTPS control plane
if using that UI remotely. The API binds loopback by default and is not a video
worker. Keep the interactive phone UI local unless you supply API authentication.
The API accepts local browser origins by default. Configure `SPICE_UI_ORIGINS`
with exact, comma-separated owned origins for an explicitly hosted UI.

Before release run the Python suite, Go checks, Node build and `spicecore doctor`.
Then verify an actual phone image/voice and an attended GPU render through QA
and review. Desktop tests and APK builds do not establish phone throughput or
notebook model quality.
