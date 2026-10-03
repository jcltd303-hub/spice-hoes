# Production deployment

## Media lanes

- Image/identity: S24 QNN runtime.
- Video: remote ComfyUI worker; quantized Wan is the low-VRAM default.
- Speech: local Piper through `SPICE_VOICE_PROVIDER=piper`.
- Lip sync: local MuseTalk 1.5 through `SPICE_LIPSYNC_PROVIDER=musetalk`.
- Wav2Lip: research/dev only. The public upstream artifacts prohibit commercial use.

Piper's maintained upstream is GPLv3, so this project invokes it as a separately
installed executable and does not vendor its source. MuseTalk code is MIT and its
upstream documentation permits commercial model use. Re-check transitive model
licenses before changing MuseTalk dependencies or weights.

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

## Required production environment

```bash
SPICE_VIDEO_PROVIDER=comfyui
COMFYUI_BASE_URL=https://...
COMFYUI_WORKFLOW=config/comfyui/wan_i2v_api.json

SPICE_VOICE_PROVIDER=piper
PIPER_BIN=/path/to/piper
PIPER_VOICE_MAP='{"zara_voss":"/models/zara.onnx"}'

SPICE_LIPSYNC_PROVIDER=musetalk
MUSETALK_DIR=/opt/MuseTalk
MUSETALK_MODEL_DIR=/opt/MuseTalk/models/musetalkV15

SUPABASE_URL=https://PROJECT.supabase.co
SUPABASE_SECRET_KEY=...
SUPABASE_BUCKET=spice-private
```

Before release run the Python unit suite, Node build, `spicecore doctor`, and a
real end-to-end render through ComfyUI -> Piper -> MuseTalk -> QA -> review.
