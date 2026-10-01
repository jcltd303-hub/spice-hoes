"""Asset generation pipeline: persona brief -> local-dream -> private asset file -> candidate."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import uuid
from pathlib import Path

from .core import Store
from .providers import LocalDreamProvider


DEFAULT_NEGATIVE = (
    "public figure likeness, child, teen, underage, youth-coded sexual styling, "
    "extra fingers, malformed hands, duplicate limbs, distorted face, waxy skin, "
    "plastic skin, 3d render, watermark, logo, text artifacts"
)


def build_asset_prompt(persona: dict, theme: str, scene: str = "", style: str = "photorealistic") -> str:
    if not theme.strip():
        raise ValueError("theme is required")
    if persona.get("fictional") is not True or int(persona.get("age", 0)) < 18:
        raise ValueError("asset generation requires a fictional adult persona")
    visual = persona.get("visual", "")
    voice = persona.get("voice", "")
    hobbies = ", ".join(persona.get("hobbies", []))
    parts = [
        f"Original fictional AI-generated adult character {persona['name']}, age {persona['age']}.",
        f"Identity anchor: {visual}.",
        f"Theme: {theme}.",
        f"Style: {style}.",
        "Photorealistic lifestyle photography, natural skin texture, visible pores, subtle asymmetry, realistic lighting, coherent anatomy.",
        "Maintain the same facial proportions, hairline, body proportions, and signature visual traits across generations.",
        "Do not resemble any real person or public figure.",
    ]
    if scene.strip():
        parts.append(f"Scene: {scene.strip()}.")
    if hobbies:
        parts.append(f"Character context: {hobbies}.")
    if voice:
        parts.append(f"Personality cue: {voice}.")
    return " ".join(parts)


def _decode_image(result: dict) -> tuple[bytes, str]:
    """Normalize common local-dream response shapes."""
    if result.get("image_base64"):
        raw = result["image_base64"]
        if raw.startswith("data:"):
            header, raw = raw.split(",", 1)
            mime = header.split(";")[0].split(":", 1)[1]
        else:
            mime = result.get("mime_type", "image/png")
        return base64.b64decode(raw, validate=True), mime

    images = result.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str):
            raw = first
            mime = "image/png"
            if raw.startswith("data:"):
                header, raw = raw.split(",", 1)
                mime = header.split(";")[0].split(":", 1)[1]
            return base64.b64decode(raw, validate=True), mime
        if isinstance(first, dict) and first.get("base64"):
            return base64.b64decode(first["base64"], validate=True), first.get("mime_type", "image/png")

    raise ValueError("local-dream response did not contain image bytes")


def _extension(mime: str) -> str:
    ext = mimetypes.guess_extension(mime or "") or ".png"
    return ".jpg" if ext == ".jpe" else ext


class AssetGenerator:
    def __init__(self, store: Store, provider: LocalDreamProvider | None = None,
                 asset_dir: str | Path = "data/assets"):
        self.store = store
        self.provider = provider or LocalDreamProvider()
        self.asset_dir = Path(asset_dir)

    def generate(self, persona: dict, theme: str, channel: str, offer: str,
                 scene: str = "", seed: int | None = None,
                 width: int = 768, height: int = 1024,
                 negative_prompt: str = DEFAULT_NEGATIVE,
                 cost_cents: int = 0) -> dict:
        if width < 256 or height < 256 or width > 4096 or height > 4096:
            raise ValueError("image dimensions must be between 256 and 4096")
        if cost_cents < 0:
            raise ValueError("cost_cents cannot be negative")

        prompt = build_asset_prompt(persona, theme, scene)
        response = self.provider.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            width=width,
            height=height,
        )
        image_bytes, mime = _decode_image(response)
        sha256 = hashlib.sha256(image_bytes).hexdigest()

        persona_dir = self.asset_dir / persona["id"]
        persona_dir.mkdir(parents=True, exist_ok=True)
        asset_id = str(uuid.uuid4())
        path = persona_dir / f"{asset_id}{_extension(mime)}"
        path.write_bytes(image_bytes)

        metadata = {
            "asset_id": asset_id,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "provider": self.provider.model_name,
            "theme": theme,
            "channel": channel,
            "offer": offer,
            "scene": scene,
            "seed": seed,
            "width": width,
            "height": height,
            "mime_type": mime,
            "sha256": sha256,
            "bytes": len(image_bytes),
            "asset_path": str(path),
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }
        meta_path = path.with_suffix(path.suffix + ".json")
        meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        candidate_id = self.store.propose(
            persona=persona,
            theme=theme,
            format="still",
            channel=channel,
            offer=offer,
            asset_uri=str(path),
            prompt=prompt,
            model=self.provider.model_name,
            seed=str(seed) if seed is not None else None,
            cost_cents=cost_cents,
        )
        self.store.record_event("asset_generated", {
            **{k: metadata[k] for k in (
                "asset_id", "persona_id", "persona_version", "provider", "theme",
                "channel", "offer", "seed", "width", "height", "mime_type",
                "sha256", "bytes", "asset_path"
            )},
            "candidate_id": candidate_id,
        })
        return {
            "candidate_id": candidate_id,
            "asset_id": asset_id,
            "asset_path": str(path),
            "metadata_path": str(meta_path),
            "sha256": sha256,
            "bytes": len(image_bytes),
            "provider": self.provider.model_name,
            "status": "proposed",
        }

    def batch(self, personas: list[dict], theme: str, channel: str, offer: str,
              count_per_persona: int = 1, seed: int | None = None,
              width: int = 768, height: int = 1024, cost_cents: int = 0) -> list[dict]:
        if count_per_persona < 1 or count_per_persona > 20:
            raise ValueError("count_per_persona must be 1..20")
        out = []
        for p_index, persona in enumerate(personas):
            for variant in range(count_per_persona):
                derived_seed = None if seed is None else seed + p_index * 1000 + variant
                out.append(self.generate(
                    persona=persona, theme=theme, channel=channel, offer=offer,
                    seed=derived_seed, width=width, height=height,
                    cost_cents=cost_cents,
                ))
        return out
