"""Asset generation pipeline: persona -> reference conditioning -> identity gate -> review candidate."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import uuid
from pathlib import Path

from .core import Store
from .identity import IdentityGate, load_reference_pack
from .providers import LocalDreamProvider
from .quality import QualityGate


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
                 asset_dir: str | Path = "data/assets",
                 reference_root: str | Path = "data/references",
                 identity_threshold: float = 0.82,
                 reference_strength: float = 0.85, quality_threshold: float = 0.78):
        self.store = store
        self.provider = provider or LocalDreamProvider()
        self.asset_dir = Path(asset_dir)
        self.reference_root = Path(reference_root)
        self.identity_threshold = identity_threshold
        self.reference_strength = reference_strength
        self.quality_gate = QualityGate(self.provider, threshold=quality_threshold)

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
        references = load_reference_pack(persona["id"], self.reference_root)
        provider_refs = [
            {"image_base64": ref["base64"], "mime_type": ref["mime_type"]}
            for ref in references
        ]
        response = self.provider.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            width=width,
            height=height,
            references=provider_refs or None,
            reference_strength=self.reference_strength,
        )
        image_bytes, mime = _decode_image(response)
        sha256 = hashlib.sha256(image_bytes).hexdigest()

        persona_dir = self.asset_dir / persona["id"]
        persona_dir.mkdir(parents=True, exist_ok=True)
        asset_id = str(uuid.uuid4())
        path = persona_dir / f"{asset_id}{_extension(mime)}"
        path.write_bytes(image_bytes)

        identity = IdentityGate(
            self.provider, threshold=self.identity_threshold
        ).score(image_bytes, mime, references)
        quality = self.quality_gate.score(image_bytes, mime, channel)

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

        rejection = None
        if identity["scored"] and not identity["passed"]:
            rejection = (
                "identity-gate",
                f"identity score {identity['score']:.4f} below {identity['threshold']:.4f}",
            )
        elif not quality["passed"]:
            rejection = (
                "quality-gate",
                f"quality score {quality['score']:.4f} below {quality['threshold']:.4f}",
            )

        if rejection:
            self.store.review(
                candidate_id,
                "rejected",
                reviewer=rejection[0],
                note=rejection[1],
            )
            status = "rejected"
        else:
            status = "proposed"

        self.store.record_event("identity_checked", {
            "candidate_id": candidate_id,
            "asset_id": asset_id,
            "persona_id": persona["id"],
            **identity,
        })

        metadata = {
            "asset_id": asset_id,
            "candidate_id": candidate_id,
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
            "reference_count": len(references),
            "reference_strength": self.reference_strength,
            "identity": identity,
            "status": status,
        }
        meta_path = path.with_suffix(path.suffix + ".json")
        meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        self.store.record_event("asset_generated", {
            "asset_id": asset_id,
            "candidate_id": candidate_id,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "provider": self.provider.model_name,
            "theme": theme,
            "channel": channel,
            "offer": offer,
            "seed": seed,
            "width": width,
            "height": height,
            "mime_type": mime,
            "sha256": sha256,
            "bytes": len(image_bytes),
            "asset_path": str(path),
            "reference_count": len(references),
            "identity_score": identity.get("score"),
            "identity_threshold": identity["threshold"],
            "status": status,
        })
        return {
            "candidate_id": candidate_id,
            "asset_id": asset_id,
            "asset_path": str(path),
            "metadata_path": str(meta_path),
            "sha256": sha256,
            "bytes": len(image_bytes),
            "provider": self.provider.model_name,
            "reference_count": len(references),
            "identity": identity,
            "status": status,
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
                    persona=persona,
                    theme=theme,
                    channel=channel,
                    offer=offer,
                    seed=derived_seed,
                    width=width,
                    height=height,
                    cost_cents=cost_cents,
                ))
        return out
