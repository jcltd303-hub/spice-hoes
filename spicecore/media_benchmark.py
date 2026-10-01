"""Side-by-side media provider benchmarking."""

from __future__ import annotations

import base64
import hashlib
import json
import time

from .providers import LocalDreamProvider, GoMediaProvider


def _decode_image(result: dict) -> tuple[bytes, str]:
    if isinstance(result.get("image_base64"), str):
        raw = result["image_base64"]
        mime = result.get("mime_type", "image/png")
        if raw.startswith("data:"):
            header, raw = raw.split(",", 1)
            mime = header.split(";")[0].split(":", 1)[1]
        return base64.b64decode(raw, validate=True), mime
    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str):
            return base64.b64decode(first, validate=True), "image/png"
        if isinstance(first, dict) and isinstance(first.get("base64"), str):
            return base64.b64decode(first["base64"], validate=True), first.get("mime_type", "image/png")
    raise ValueError("provider returned no image payload")


def benchmark_media(prompt: str, negative_prompt: str = "", seed: int = 42,
                    width: int = 768, height: int = 1024,
                    references: list[dict] | None = None,
                    reference_strength: float = 0.85) -> dict:
    providers = [
        ("local-dream", LocalDreamProvider()),
        ("go-media", GoMediaProvider()),
    ]
    results = []
    for name, provider in providers:
        started = time.perf_counter()
        row = {
            "provider": name,
            "model": provider.model_name,
            "seed": seed,
            "width": width,
            "height": height,
            "success": False,
        }
        try:
            generated = provider.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                width=width,
                height=height,
                references=references,
                reference_strength=reference_strength,
            )
            image_bytes, mime = _decode_image(generated)
            row.update({
                "success": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": len(image_bytes),
                "mime_type": mime,
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            })
            if references:
                try:
                    identity = provider.score_identity(
                        image_base64=base64.b64encode(image_bytes).decode("ascii"),
                        image_mime_type=mime,
                        references=references,
                    )
                    row["identity_score"] = float(identity.get("score")) if identity.get("score") is not None else None
                    for key in (
                        "metric", "model", "alignment", "npu", "embedding_dimensions",
                        "latency_ms", "detector_latency_ms", "reference_count",
                    ):
                        if identity.get(key) is not None:
                            row[f"identity_{key}"] = identity[key]
                except Exception as exc:
                    row["identity_error"] = f"{type(exc).__name__}: {exc}"
            try:
                quality = provider.score_quality(
                    image_base64=base64.b64encode(image_bytes).decode("ascii"),
                    image_mime_type=mime,
                    channel="benchmark",
                )
                numeric = [
                    float(quality[k]) for k in ("anatomy","hands","face_visibility","realism","composition")
                    if quality.get(k) is not None
                ]
                row["quality_score"] = round(sum(numeric) / len(numeric), 6) if numeric else None
            except Exception as exc:
                row["quality_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            row["error"] = f"{type(exc).__name__}: {exc}"
        results.append(row)

    successes = [r for r in results if r["success"]]
    fastest = min(successes, key=lambda r: r["latency_ms"])["provider"] if successes else None
    best_quality = max(
        (r for r in successes if r.get("quality_score") is not None),
        key=lambda r: r["quality_score"],
        default=None,
    )
    return {
        "prompt": prompt,
        "seed": seed,
        "results": results,
        "summary": {
            "fastest_provider": fastest,
            "highest_quality_provider": best_quality["provider"] if best_quality else None,
        },
    }
