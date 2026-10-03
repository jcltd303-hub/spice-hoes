"""ComfyUI HTTP API video provider for ephemeral Colab/Kaggle GPU workers."""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import random
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .video import VideoProvider


TOKENS = {
    "__SPICE_PROMPT__": "prompt",
    "__SPICE_IMAGE__": "image",
    "__SPICE_SEED__": "seed",
    "__SPICE_WIDTH__": "width",
    "__SPICE_HEIGHT__": "height",
    "__SPICE_FRAMES__": "frames",
    "__SPICE_FPS__": "fps",
}


class ComfyUIVideoProvider(VideoProvider):
    """Submit API-format workflows to a standard ComfyUI server."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        workflow_path: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        poll_seconds: Optional[float] = None,
        bearer_token: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("COMFYUI_BASE_URL", "")).rstrip("/")
        self.workflow_path = workflow_path or os.getenv(
            "COMFYUI_WORKFLOW", "config/comfyui/wan21_i2v_q4_api.json"
        )
        self.timeout_seconds = int(timeout_seconds or os.getenv("COMFYUI_TIMEOUT_SECONDS", "900"))
        self.poll_seconds = float(poll_seconds or os.getenv("COMFYUI_POLL_SECONDS", "2"))
        self.bearer_token = bearer_token or os.getenv("COMFYUI_BEARER_TOKEN", "")
        self.jobs: Dict[str, Dict[str, Any]] = {}
        if not self.base_url:
            raise RuntimeError("COMFYUI_BASE_URL is required for the comfyui video provider")

    @property
    def model_name(self) -> str:
        return f"comfyui:{Path(self.workflow_path).stem}"

    def _headers(self, json_body: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _json(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers=self._headers(json_body=payload is not None),
        )
        with urllib.request.urlopen(req, timeout=min(self.timeout_seconds, 120)) as response:
            return json.loads(response.read().decode("utf-8"))

    def _upload_image(self, image_uri: str) -> str:
        path = Path(image_uri.replace("file://", "", 1))
        if not path.is_file():
            raise FileNotFoundError(f"ComfyUI source image must be a local file: {image_uri}")
        boundary = f"----spice{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{boundary}--\r\n".encode(),
        ]
        headers = self._headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=b"".join(chunks),
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
        return str(result.get("name") or path.name)

    def _load_workflow(self) -> dict:
        path = Path(self.workflow_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"ComfyUI API workflow not found: {path}. Export an API-format workflow "
                "from ComfyUI and set COMFYUI_WORKFLOW."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("ComfyUI API workflow must be a JSON object")
        return data

    @staticmethod
    def _dims(aspect_ratio: str) -> tuple[int, int]:
        return (576, 1024) if aspect_ratio == "9:16" else (1024, 576)

    @staticmethod
    def _inject(workflow: dict, *, prompt: str, image: str, seed: int,
                width: int, height: int, frames: int, fps: int) -> dict:
        values = {
            "prompt": prompt,
            "image": image,
            "seed": seed,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
        }
        out = copy.deepcopy(workflow)
        for node in out.values():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", ""))
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key, value in list(inputs.items()):
                if isinstance(value, str) and value in TOKENS:
                    inputs[key] = values[TOKENS[value]]
            if class_type == "LoadImage" and "image" in inputs:
                inputs["image"] = image
            for key in ("seed", "noise_seed"):
                if key in inputs and not isinstance(inputs[key], list):
                    inputs[key] = seed
            for key, val in (("width", width), ("height", height), ("fps", fps)):
                if key in inputs and not isinstance(inputs[key], list):
                    inputs[key] = val
            for key in ("length", "video_length", "num_frames", "frames"):
                if key in inputs and not isinstance(inputs[key], list):
                    inputs[key] = frames
            for key in ("prompt", "positive_prompt"):
                if key in inputs and isinstance(inputs[key], str):
                    inputs[key] = prompt
        return out

    @staticmethod
    def _find_outputs(history: dict) -> Iterable[dict]:
        outputs = history.get("outputs", {}) if isinstance(history, dict) else {}
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for key in ("videos", "gifs", "images"):
                items = node_output.get(key, [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("filename"):
                            yield item

    def image_to_video(
        self,
        image_uri: str,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
        motion: str = "subtle push-in",
        seed: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        width, height = self._dims(aspect_ratio)
        width = int(kwargs.get("width", width))
        height = int(kwargs.get("height", height))
        fps = int(kwargs.get("fps", 24))
        frames = int(kwargs.get("frames", max(17, round(float(duration_seconds) * fps))))
        actual_seed = int(seed if seed is not None else random.randrange(0, 2**31))
        uploaded = self._upload_image(image_uri)
        workflow = self._inject(
            self._load_workflow(),
            prompt=f"{prompt}. Motion: {motion}",
            image=uploaded,
            seed=actual_seed,
            width=width,
            height=height,
            frames=frames,
            fps=fps,
        )
        submitted = self._json("POST", "/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex})
        prompt_id = str(submitted.get("prompt_id", ""))
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {submitted}")
        job_id = f"comfy-{prompt_id}"
        result = {
            "job_id": job_id,
            "prompt_id": prompt_id,
            "status": "queued",
            "provider": self.model_name,
            "cost_cents": 0,
            "seed": actual_seed,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "workflow": self.workflow_path,
        }
        self.jobs[job_id] = result
        return result

    def text_image_to_video(self, prompt: str, image_uri: str,
                            duration_seconds: float = 5.0,
                            aspect_ratio: str = "9:16", **kwargs) -> Dict[str, Any]:
        return self.image_to_video(
            image_uri=image_uri, prompt=prompt,
            duration_seconds=duration_seconds, aspect_ratio=aspect_ratio, **kwargs
        )

    def talking_head(self, image_uri: str, audio_uri: str, **kwargs) -> Dict[str, Any]:
        raise RuntimeError(
            "Talking-head generation needs an audio-conditioned ComfyUI workflow; "
            "use image_to_video for the current Wan/LTX lane."
        )

    def status(self, job_id: str) -> Dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(f"Unknown job_id: {job_id}")
        history = self._json("GET", f"/history/{urllib.parse.quote(job['prompt_id'])}")
        item = history.get(job["prompt_id"], {})
        if item and item.get("outputs"):
            job["status"] = "completed"
            job["history"] = item
        elif item.get("status", {}).get("status_str") == "error":
            job["status"] = "failed"
            job["history"] = item
        else:
            job["status"] = "running"
        return dict(job)

    def download(self, job_id: str, destination_path: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        latest = self.status(job_id)
        while latest["status"] not in ("completed", "failed"):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"ComfyUI job timed out: {job_id}")
            time.sleep(self.poll_seconds)
            latest = self.status(job_id)
        if latest["status"] == "failed":
            raise RuntimeError(f"ComfyUI job failed: {latest.get('history')}")
        candidates = list(self._find_outputs(latest.get("history", {})))
        if not candidates:
            raise RuntimeError("ComfyUI completed without a downloadable output")
        video = next(
            (x for x in candidates if str(x["filename"]).lower().endswith((".mp4", ".webm", ".mov"))),
            candidates[0],
        )
        query = urllib.parse.urlencode({
            "filename": video["filename"],
            "subfolder": video.get("subfolder", ""),
            "type": video.get("type", "output"),
        })
        req = urllib.request.Request(f"{self.base_url}/view?{query}", headers=self._headers())
        Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(req, timeout=120) as response:
            Path(destination_path).write_bytes(response.read())
        return destination_path
