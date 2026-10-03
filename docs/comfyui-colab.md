# ComfyUI Google Colab video worker

The production Spice video lane is pinned to **Wan2.1 I2V 14B GGUF** through ComfyUI-GGUF.

- Quality default: `config/comfyui/wan21_i2v_q4_api.json` using Q4_K_M.
- Low-VRAM fallback: `config/comfyui/wan21_i2v_q3_api.json` using Q3_K_M.
- Both are ComfyUI API-format graphs and accept the Spice runtime placeholders.
- The official ComfyUI Wan graph structure is retained: Wan image conditioning, CLIP Vision, ModelSamplingSD3, KSampler, VAE decode, CreateVideo, SaveVideo.

## Colab

Open `notebooks/spice_comfyui_colab.ipynb`, choose a GPU runtime, and run all cells. It:

1. installs current ComfyUI and ComfyUI-GGUF;
2. downloads the selected public Wan GGUF plus official text encoder, CLIP Vision encoder and VAE;
3. starts ComfyUI in low-VRAM mode;
4. checks `/object_info` for every required node before accepting traffic;
5. exposes the attended session through a temporary Cloudflare Quick Tunnel.

The default model set is approximately 19 GB of downloads with Q4_K_M. Set `WAN_QUANT=Q3_K_M` before the model-download cell for the smaller diffusion model.

## Runtime

```bash
export SPICE_VIDEO_PROVIDER=comfyui
export COMFYUI_BASE_URL='https://YOUR-RANDOM.trycloudflare.com'
export COMFYUI_WORKFLOW='config/comfyui/wan21_i2v_q4_api.json'
```

For the lower-memory profile:

```bash
export COMFYUI_WORKFLOW='config/comfyui/wan21_i2v_q3_api.json'
```

The provider uploads the approved source image, injects prompt/image/seed/dimensions/frame count/fps, POSTs the graph to `/prompt`, polls `/history/{prompt_id}`, downloads the MP4 from `/view`, and continues into Piper speech, MuseTalk lip sync, FFmpeg/QA, and human review.

## Security

Cloudflare Quick Tunnel is transport, not authentication. Use it only for attended ephemeral Colab sessions. For unattended production put an authenticated reverse proxy in front of ComfyUI and set `COMFYUI_BEARER_TOKEN` to the proxy credential.

Colab availability and model/service terms remain external constraints; the repository does not assume unlimited free GPU availability.
