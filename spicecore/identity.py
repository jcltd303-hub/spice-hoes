"""Reference-pack loading and identity consistency scoring for generated assets."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from .providers import ProviderError


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def load_reference_pack(persona_id: str, reference_root: str | Path = "data/references",
                        limit: int = 6) -> list[dict]:
    root = Path(reference_root) / persona_id
    if not root.exists():
        return []
    refs = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            refs.append({
                "path": str(path),
                "mime_type": {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }.get(path.suffix.lower(), "image/png"),
                "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            })
            if len(refs) >= limit:
                break
    return refs


class IdentityGate:
    def __init__(self, provider, threshold: float = 0.82):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("identity threshold must be between 0 and 1")
        self.provider = provider
        self.threshold = threshold

    def score(self, generated_bytes: bytes, generated_mime: str,
              references: list[dict]) -> dict:
        if not references:
            return {
                "scored": False,
                "score": None,
                "threshold": self.threshold,
                "passed": False,
                "reason": "no_reference_pack",
            }

        result = self.provider.score_identity(
            image_base64=base64.b64encode(generated_bytes).decode("ascii"),
            image_mime_type=generated_mime,
            references=[
                {"image_base64": ref["base64"], "mime_type": ref["mime_type"]}
                for ref in references
            ],
        )
        try:
            score = float(result["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("identity scorer returned no numeric score") from exc
        metric = result.get("metric", "score")
        if metric == "cosine":
            score = max(-1.0, min(1.0, score))
        else:
            score = max(0.0, min(1.0, score))
        return {
            "scored": True,
            "score": score,
            "metric": metric,
            "threshold": self.threshold,
            "passed": score >= self.threshold,
            "reference_count": len(references),
            "scorer": result.get("model", "media:identity"),
            "alignment": result.get("alignment"),
            "npu": result.get("npu"),
            "embedding_dimensions": result.get("embedding_dimensions"),
            "latency_ms": result.get("latency_ms"),
            "detector_latency_ms": result.get("detector_latency_ms"),
        }
