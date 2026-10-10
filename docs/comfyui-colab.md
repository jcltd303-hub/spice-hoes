# Optional self-hosted ComfyUI video worker

The default free GPU path uses [attended notebook ZIP jobs](free-gpu-media.md).
`notebooks/spice_comfyui_colab.ipynb` is a compatibility copy of that notebook;
it no longer starts a ComfyUI server or tunnel in Colab.

Use the existing ComfyUI adapter when you already have an installed GPU worker:

```bash
export SPICE_VIDEO_PROVIDER=comfyui
export COMFYUI_BASE_URL=http://127.0.0.1:8188
export COMFYUI_WORKFLOW=config/comfyui/wan21_i2v_q4_api.json
# Select this graph for the smaller Q3 model:
# export COMFYUI_WORKFLOW=config/comfyui/wan21_i2v_q3_api.json
```

These API graphs require ComfyUI-GGUF plus the named Wan2.1 I2V diffusion model,
text encoder, CLIP Vision encoder and VAE. Inspect your worker's `/object_info`
and installed weights before rendering. The adapter uploads the reviewed image,
submits the graph, polls its history and downloads its generated MP4. Missing
nodes, models or outputs fail rather than becoming a mock video.

For a remote worker, use your authenticated HTTPS proxy and set
`COMFYUI_BEARER_TOKEN` to its credential. Native ComfyUI has no bearer auth.
Speech still defaults to the local Android companion, and lip sync defaults to
attended GPU batches. Set Piper/MuseTalk explicitly for an installed desktop lane.
