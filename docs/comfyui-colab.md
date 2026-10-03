# ComfyUI Google Colab video worker

The Spice pipeline can use any ComfyUI **API-format** image-to-video workflow over the standard HTTP API. This keeps model choice outside the application: Wan, LTX, GGUF, FP8, and later workflows are selected by changing `COMFYUI_WORKFLOW`.

## 1. Start the Colab worker

Open `notebooks/spice_comfyui_colab.ipynb` in Google Colab, choose a GPU runtime, and run the cells. The notebook installs current ComfyUI plus `ComfyUI-GGUF`, starts port 8188, and creates a temporary Cloudflare Quick Tunnel without a generation API token.

Colab/Kaggle availability, GPU type, session duration, and acceptable-use rules are controlled by those services and can change. Open-source software does not exempt use from their terms or from model licenses.

## 2. Choose a workflow

For limited VRAM, start with a Wan image-to-video workflow using a quantized diffusion model. For LTX, use a workflow/checkpoint matched to the GPU memory available in the session.

In ComfyUI, load the desired workflow, verify it runs once, then export **Save (API Format)**. Store that JSON locally (not secrets or model weights) and set:

```bash
export SPICE_VIDEO_PROVIDER=comfyui
export COMFYUI_BASE_URL='https://YOUR-RANDOM.trycloudflare.com'
export COMFYUI_WORKFLOW='config/comfyui/wan_i2v_api.json'
```

The provider recognizes these optional literal placeholders inside node inputs:

```text
__SPICE_PROMPT__
__SPICE_IMAGE__
__SPICE_SEED__
__SPICE_WIDTH__
__SPICE_HEIGHT__
__SPICE_FRAMES__
__SPICE_FPS__
```

It also automatically fills common `LoadImage`, seed, width, height, frame-count, and fps inputs.

## 3. Pipeline behavior

`MediaPipeline` now resolves the video backend from `SPICE_VIDEO_PROVIDER`. For each scene it uploads the source image, injects runtime values, POSTs the graph to `/prompt`, polls `/history/{prompt_id}`, downloads the output with `/view`, and then continues through captions, FFmpeg assembly, technical QA, and human review.

ComfyUI jobs report zero API-token cost. GPU/session costs, if any, still belong in experiment accounting.

## Security

A Quick Tunnel gives a temporary URL but native ComfyUI does not provide bearer authentication. Use it only for an attended ephemeral session, do not commit the tunnel URL, terminate the Colab runtime afterward, and place an authenticated reverse proxy in front of ComfyUI before unattended operation.
