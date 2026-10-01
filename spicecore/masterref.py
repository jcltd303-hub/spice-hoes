"""Build and promote multi-angle master reference packs for fictional adult personas."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .assetgen import DEFAULT_NEGATIVE, _decode_image, _extension
from .core import Store
from .providers import LocalDreamProvider


REFERENCE_VIEWS = (
    ("front", "front-facing portrait, neutral expression, shoulders visible, direct eye contact"),
    ("left_profile", "clean left side profile, same hairstyle and proportions"),
    ("right_profile", "clean right side profile, same hairstyle and proportions"),
    ("hair_back", "rear three-quarter view emphasizing hair texture and hairline"),
    ("eyes_closeup", "tight eye and upper-face close-up, neutral expression"),
    ("full_body", "full-body standing portrait, neutral pose, fitted simple outfit showing proportions"),
)


def master_prompt(persona: dict, view_instruction: str) -> str:
    if persona.get("fictional") is not True or int(persona.get("age", 0)) < 18:
        raise ValueError("master references require a fictional adult persona")
    return (
        f"Original fictional AI-generated adult character {persona['name']}, age {persona['age']}. "
        f"Identity anchor: {persona.get('visual', '')}. "
        f"Reference-sheet capture: {view_instruction}. "
        "Plain neutral background, soft even lighting, 35mm photographic realism, natural skin texture, "
        "visible pores, subtle asymmetry, realistic anatomy. No accessories obscuring facial landmarks. "
        "Keep facial geometry, hairline, body proportions, skin tone, and signature traits stable. "
        "Do not resemble any real person or public figure."
    )


class MasterReferenceBuilder:
    def __init__(self, store: Store, provider: LocalDreamProvider | None = None,
                 staging_root: str | Path = "data/reference_candidates",
                 reference_root: str | Path = "data/references",
                 identity_threshold: float = 0.84,
                 reference_strength: float = 0.90):
        self.store = store
        self.provider = provider or LocalDreamProvider()
        self.staging_root = Path(staging_root)
        self.reference_root = Path(reference_root)
        self.identity_threshold = identity_threshold
        self.reference_strength = reference_strength
        if not 0 <= identity_threshold <= 1:
            raise ValueError("identity_threshold must be between 0 and 1")

    def _generate(self, prompt: str, seed: int | None, refs: list[dict] | None = None) -> tuple[bytes, str]:
        response = self.provider.generate_image(
            prompt=prompt,
            negative_prompt=DEFAULT_NEGATIVE,
            seed=seed,
            width=768,
            height=1024,
            references=refs,
            reference_strength=self.reference_strength,
        )
        return _decode_image(response)

    def build(self, persona: dict, seed: int | None = None) -> dict:
        run_id = str(uuid.uuid4())
        out_dir = self.staging_root / persona["id"] / run_id
        out_dir.mkdir(parents=True, exist_ok=False)

        files = []
        scores = []
        anchor_ref = None

        for index, (view, instruction) in enumerate(REFERENCE_VIEWS):
            derived_seed = None if seed is None else seed + index
            refs = [anchor_ref] if anchor_ref else None
            image_bytes, mime = self._generate(
                master_prompt(persona, instruction),
                seed=derived_seed,
                refs=refs,
            )
            path = out_dir / f"{index:02d}_{view}{_extension(mime)}"
            path.write_bytes(image_bytes)
            sha = hashlib.sha256(image_bytes).hexdigest()

            if anchor_ref is None:
                anchor_ref = {
                    "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                    "mime_type": mime,
                }
                score = 1.0
                passed = True
                scorer = "self-anchor"
            else:
                scored = self.provider.score_identity(
                    image_base64=base64.b64encode(image_bytes).decode("ascii"),
                    image_mime_type=mime,
                    references=[anchor_ref],
                )
                score = max(0.0, min(1.0, float(scored["score"])))
                passed = score >= self.identity_threshold
                scorer = scored.get("model", "local-dream:identity")

            files.append({
                "view": view,
                "path": str(path),
                "mime_type": mime,
                "sha256": sha,
                "seed": derived_seed,
                "identity_score": score,
                "passed": passed,
                "scorer": scorer,
            })
            scores.append(score)

        ready = all(item["passed"] for item in files)
        manifest = {
            "run_id": run_id,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider.model_name,
            "identity_threshold": self.identity_threshold,
            "reference_strength": self.reference_strength,
            "mean_identity_score": round(sum(scores) / len(scores), 6),
            "ready_for_promotion": ready,
            "files": files,
        }
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        self.store.record_event("master_reference_pack_proposed", {
            "run_id": run_id,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "manifest_path": str(manifest_path),
            "ready_for_promotion": ready,
            "mean_identity_score": manifest["mean_identity_score"],
            "identity_threshold": self.identity_threshold,
        })
        return manifest

    def promote(self, manifest_path: str | Path) -> dict:
        manifest_path = Path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("ready_for_promotion"):
            raise ValueError("reference pack is not ready for promotion")
        persona_id = manifest["persona_id"]
        destination = self.reference_root / persona_id
        destination.mkdir(parents=True, exist_ok=True)

        # Replace only generated image files in the canonical pack; keep unrelated files untouched.
        for existing in destination.iterdir():
            if existing.is_file() and existing.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                existing.unlink()

        promoted = []
        for item in manifest["files"]:
            source = Path(item["path"])
            target = destination / source.name
            shutil.copy2(source, target)
            promoted.append(str(target))

        canonical_manifest = {
            **manifest,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promoted_files": promoted,
        }
        canonical_path = destination / "manifest.json"
        canonical_path.write_text(json.dumps(canonical_manifest, indent=2, sort_keys=True), encoding="utf-8")

        self.store.record_event("master_reference_pack_promoted", {
            "run_id": manifest["run_id"],
            "persona_id": persona_id,
            "manifest_path": str(canonical_path),
            "file_count": len(promoted),
            "mean_identity_score": manifest["mean_identity_score"],
        })
        return {
            "persona_id": persona_id,
            "run_id": manifest["run_id"],
            "reference_dir": str(destination),
            "manifest_path": str(canonical_path),
            "file_count": len(promoted),
            "mean_identity_score": manifest["mean_identity_score"],
        }
