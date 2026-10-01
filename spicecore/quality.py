"""Local and provider-assisted visual quality checks for generated assets."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import os
import shutil
import subprocess
from statistics import mean


def _post_quality(base_url: str, token: str, payload: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/quality/score",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"quality scorer failed: {exc}") from exc


class QualityGate:
    def __init__(self, provider, threshold: float = 0.78):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("quality threshold must be between 0 and 1")
        self.provider = provider
        self.threshold = threshold

    @staticmethod
    def _tool_path() -> str | None:
        configured = os.getenv("SPICE_IMAGE_TOOL", "").strip()
        if configured:
            return configured
        local = os.path.join(os.getcwd(), "bin", "spiceimg")
        if os.path.isfile(local) and os.access(local, os.X_OK):
            return local
        return shutil.which("spiceimg")

    @staticmethod
    def local_metrics(image_bytes: bytes) -> dict:
        tool = QualityGate._tool_path()
        if not tool:
            return {
                "available": False,
                "backend": "go-tool-missing",
                "width": None,
                "height": None,
                "brightness": None,
                "sharpness": None,
                "contrast": None,
                "resolution_score": None,
                "exposure_score": None,
                "local_score": None,
            }
        try:
            proc = subprocess.run(
                [tool, "metrics"],
                input=image_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=30,
            )
            result = json.loads(proc.stdout.decode("utf-8"))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"go image metrics failed: {exc}") from exc
        required = (
            "available", "backend", "width", "height", "brightness", "sharpness",
            "contrast", "resolution_score", "exposure_score", "local_score",
        )
        if not all(key in result for key in required):
            raise RuntimeError("go image metrics returned incomplete payload")
        return result

    def _provider_score(self, image_b64: str, mime_type: str, channel: str) -> dict:
        if hasattr(self.provider, "score_quality"):
            return self.provider.score_quality(
                image_base64=image_b64,
                image_mime_type=mime_type,
                channel=channel,
            )
        base_url = getattr(self.provider, "base_url", "")
        if not base_url:
            raise RuntimeError("quality provider exposes neither score_quality nor base_url")
        return _post_quality(
            base_url,
            getattr(self.provider, "token", ""),
            {
                "image_base64": image_b64,
                "image_mime_type": mime_type,
                "channel": channel,
            },
        )

    def score(self, image_bytes: bytes, mime_type: str, channel: str = "") -> dict:
        local = self.local_metrics(image_bytes)
        provider_result = self._provider_score(
            base64.b64encode(image_bytes).decode("ascii"),
            mime_type,
            channel,
        )
        required = ("anatomy", "hands", "face_visibility", "realism", "composition")
        metrics = {}
        for key in required:
            try:
                metrics[key] = max(0.0, min(1.0, float(provider_result[key])))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"quality scorer missing numeric {key}") from exc

        provider_score = mean(metrics.values())
        overall = (
            0.35 * local["local_score"] + 0.65 * provider_score
            if local.get("local_score") is not None
            else provider_score
        )
        passed = overall >= self.threshold and min(
            metrics["anatomy"], metrics["face_visibility"], metrics["realism"]
        ) >= 0.65

        return {
            "scored": True,
            "score": round(overall, 6),
            "threshold": self.threshold,
            "passed": passed,
            "local": local,
            "provider": {
                **{k: round(v, 6) for k, v in metrics.items()},
                "score": round(provider_score, 6),
                "model": provider_result.get("model", "local-dream:quality"),
            },
            "reasons": [
                key for key, value in metrics.items()
                if value < 0.65
            ],
        }
