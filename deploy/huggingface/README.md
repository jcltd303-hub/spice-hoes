---
title: Spice Hoes Control Plane
emoji: 🌶️
colorFrom: pink
colorTo: purple
sdk: static
app_build_command: npm run build
app_file: dist/index.html
---

Static operator dashboard target.

A free static Space can host only the built frontend. It does not run the Python
control plane, Piper, MuseTalk, ComfyUI, or SQLite. Point the frontend at a
separately hosted API when using this mode.

For a full container deployment use `deploy/huggingface/Dockerfile` on a
Docker-capable Space/host with enough CPU/GPU resources.
