"""Provider adapters for compute lanes: local-dream, video, voice, and lipsync."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from .video import VideoProvider, MockVideoProvider, LumaVideoProvider, video_provider_from_env
from .comfyui import ComfyUIVideoProvider
from .voice import VoiceProvider, VoiceProfile, MockVoiceProvider, ElevenLabsVoiceProvider, CANONICAL_VOICE_PROFILES
from .lipsync import LipSyncProvider, MockLipSyncProvider, SyncLabsLipSyncProvider


class ProviderError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc


def _validate_b64(value: str) -> None:
    raw = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    base64.b64decode(raw, validate=True)


class LocalDreamProvider:
    """Adapter for local-dream generation and local identity scoring."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("LOCAL_DREAM_URL", "http://127.0.0.1:7860")).rstrip("/")
        self.token = token or os.getenv("LOCAL_DREAM_TOKEN", "")

    @property
    def model_name(self) -> str:
        return "local-dream:s24"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def generate_image(self, prompt: str, negative_prompt: str = "", seed: int | None = None,
                       width: int = 768, height: int = 1024,
                       references: list[dict] | None = None,
                       reference_strength: float = 0.85) -> dict:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
        }
        if seed is not None:
            payload["seed"] = seed
        if references:
            payload["references"] = references
            payload["reference_strength"] = reference_strength

        data = _post_json(
            f"{self.base_url}/generate",
            payload,
            self._headers(),
            timeout=180,
        )
        if isinstance(data.get("image_base64"), str):
            _validate_b64(data["image_base64"])
        elif isinstance(data.get("images"), list) and data["images"]:
            first = data["images"][0]
            if isinstance(first, str):
                _validate_b64(first)
            elif isinstance(first, dict) and isinstance(first.get("base64"), str):
                _validate_b64(first["base64"])
            else:
                raise ProviderError("local-dream returned unsupported images[] payload")
        else:
            raise ProviderError("local-dream returned no image payload")
        return data

    def score_identity(self, image_base64: str, image_mime_type: str,
                       references: list[dict]) -> dict:
        if not references:
            raise ProviderError("identity scoring requires at least one reference")
        return _post_json(
            f"{self.base_url}/identity/score",
            {
                "image_base64": image_base64,
                "image_mime_type": image_mime_type,
                "references": references,
            },
            self._headers(),
            timeout=120,
        )


__all__ = [
    "ProviderError",
    "LocalDreamProvider",
    "VideoProvider",
    "MockVideoProvider",
    "LumaVideoProvider",
    "ComfyUIVideoProvider",
    "video_provider_from_env",
    "VoiceProvider",
    "VoiceProfile",
    "MockVoiceProvider",
    "ElevenLabsVoiceProvider",
    "CANONICAL_VOICE_PROFILES",
    "LipSyncProvider",
    "MockLipSyncProvider",
    "SyncLabsLipSyncProvider",
]
