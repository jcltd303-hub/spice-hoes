"""Local and provider-assisted visual quality checks for generated assets."""

from __future__ import annotations

import base64
import io
from statistics import mean

from PIL import Image, ImageFilter, ImageStat


class QualityGate:
    def __init__(self, provider, threshold: float = 0.78):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("quality threshold must be between 0 and 1")
        self.provider = provider
        self.threshold = threshold

    @staticmethod
    def local_metrics(image_bytes: bytes) -> dict:
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb = image.convert("RGB")
            gray = rgb.convert("L")
            stat = ImageStat.Stat(gray)
            brightness = stat.mean[0] / 255.0
            contrast = stat.stddev[0] / 128.0

            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            sharpness = min(1.0, edge_stat.stddev[0] / 64.0)

            width, height = rgb.size
            megapixels = (width * height) / 1_000_000
            resolution_score = min(1.0, megapixels / 0.7)

            exposure_score = max(0.0, 1.0 - abs(brightness - 0.5) / 0.5)
            contrast_score = min(1.0, contrast)
            local_score = mean((sharpness, exposure_score, contrast_score, resolution_score))
            return {
                "width": width,
                "height": height,
                "brightness": round(brightness, 6),
                "sharpness": round(sharpness, 6),
                "contrast": round(contrast_score, 6),
                "resolution_score": round(resolution_score, 6),
                "exposure_score": round(exposure_score, 6),
                "local_score": round(local_score, 6),
            }

    def score(self, image_bytes: bytes, mime_type: str, channel: str = "") -> dict:
        local = self.local_metrics(image_bytes)
        provider_result = self.provider.score_quality(
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            image_mime_type=mime_type,
            channel=channel,
        )
        required = ("anatomy", "hands", "face_visibility", "realism", "composition")
        metrics = {}
        for key in required:
            try:
                metrics[key] = max(0.0, min(1.0, float(provider_result[key])))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"quality scorer missing numeric {key}") from exc

        provider_score = mean(metrics.values())
        overall = 0.35 * local["local_score"] + 0.65 * provider_score
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
