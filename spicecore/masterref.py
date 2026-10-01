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
                 reference_strength: float = 0.90,
                 anchor_candidates: int = 3,
                 attempts_per_view: int = 2):
        self.store = store
        self.provider = provider or LocalDreamProvider()
        self.staging_root = Path(staging_root)
        self.reference_root = Path(reference_root)
        self.identity_threshold = identity_threshold
        self.reference_strength = reference_strength
        self.anchor_candidates = anchor_candidates
        self.attempts_per_view = attempts_per_view
        if not 0 <= identity_threshold <= 1:
            raise ValueError("identity_threshold must be between 0 and 1")
        if anchor_candidates < 2 or anchor_candidates > 8:
            raise ValueError("anchor_candidates must be 2..8")
        if attempts_per_view < 1 or attempts_per_view > 8:
            raise ValueError("attempts_per_view must be 1..8")

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

    @staticmethod
    def _ref(image_bytes: bytes, mime: str) -> dict:
        return {
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "mime_type": mime,
        }

    def _identity_score(self, image_bytes: bytes, mime: str, refs: list[dict]) -> float:
        scored = self.provider.score_identity(
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            image_mime_type=mime,
            references=refs,
        )
        return max(0.0, min(1.0, float(scored["score"])))

    def _select_anchor(self, persona: dict, out_dir: Path, seed: int | None) -> tuple[dict, list[dict]]:
        candidates = []
        prompt = master_prompt(persona, REFERENCE_VIEWS[0][1])
        for i in range(self.anchor_candidates):
            derived_seed = None if seed is None else seed + i
            image_bytes, mime = self._generate(prompt, derived_seed)
            candidates.append({
                "bytes": image_bytes,
                "mime": mime,
                "seed": derived_seed,
                "candidate": i,
            })

        for i, candidate in enumerate(candidates):
            refs = [self._ref(other["bytes"], other["mime"]) for j, other in enumerate(candidates) if j != i]
            candidate["consensus_score"] = self._identity_score(candidate["bytes"], candidate["mime"], refs)

        selected = max(candidates, key=lambda x: (x["consensus_score"], -x["candidate"]))
        diagnostics = []
        for candidate in candidates:
            suffix = _extension(candidate["mime"])
            path = out_dir / f"anchor_candidate_{candidate['candidate']:02d}{suffix}"
            path.write_bytes(candidate["bytes"])
            diagnostics.append({
                "path": str(path),
                "seed": candidate["seed"],
                "consensus_score": candidate["consensus_score"],
                "selected": candidate is selected,
            })
        return selected, diagnostics

    def build(self, persona: dict, seed: int | None = None) -> dict:
        run_id = str(uuid.uuid4())
        out_dir = self.staging_root / persona["id"] / run_id
        out_dir.mkdir(parents=True, exist_ok=False)

        anchor, anchor_diagnostics = self._select_anchor(persona, out_dir, seed)
        anchor_ref = self._ref(anchor["bytes"], anchor["mime"])

        files = []
        front_path = out_dir / f"00_front{_extension(anchor['mime'])}"
        front_path.write_bytes(anchor["bytes"])
        files.append({
            "view": "front",
            "path": str(front_path),
            "mime_type": anchor["mime"],
            "sha256": hashlib.sha256(anchor["bytes"]).hexdigest(),
            "seed": anchor["seed"],
            "identity_score": anchor["consensus_score"],
            "passed": anchor["consensus_score"] >= self.identity_threshold,
            "scorer": "identity-consensus-medoid",
            "attempts": self.anchor_candidates,
        })

        seed_cursor = self.anchor_candidates
        for view_index, (view, instruction) in enumerate(REFERENCE_VIEWS[1:], start=1):
            attempts = []
            prompt = master_prompt(persona, instruction)
            for attempt in range(self.attempts_per_view):
                derived_seed = None if seed is None else seed + seed_cursor
                seed_cursor += 1
                image_bytes, mime = self._generate(prompt, derived_seed, refs=[anchor_ref])
                score = self._identity_score(image_bytes, mime, [anchor_ref])
                attempts.append({
                    "bytes": image_bytes,
                    "mime": mime,
                    "seed": derived_seed,
                    "score": score,
                    "attempt": attempt,
                })

            selected = max(attempts, key=lambda x: (x["score"], -x["attempt"]))
            path = out_dir / f"{view_index:02d}_{view}{_extension(selected['mime'])}"
            path.write_bytes(selected["bytes"])
            files.append({
                "view": view,
                "path": str(path),
                "mime_type": selected["mime"],
                "sha256": hashlib.sha256(selected["bytes"]).hexdigest(),
                "seed": selected["seed"],
                "identity_score": selected["score"],
                "passed": selected["score"] >= self.identity_threshold,
                "scorer": "local-dream:identity",
                "attempts": self.attempts_per_view,
                "attempt_scores": [round(x["score"], 6) for x in attempts],
            })

        scores = [item["identity_score"] for item in files]
        ready = all(item["passed"] for item in files)
        manifest = {
            "run_id": run_id,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider.model_name,
            "identity_threshold": self.identity_threshold,
            "reference_strength": self.reference_strength,
            "anchor_candidates": self.anchor_candidates,
            "attempts_per_view": self.attempts_per_view,
            "anchor_diagnostics": anchor_diagnostics,
            "mean_identity_score": round(sum(scores) / len(scores), 6),
            "minimum_identity_score": round(min(scores), 6),
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
            "minimum_identity_score": manifest["minimum_identity_score"],
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
            "minimum_identity_score": manifest["minimum_identity_score"],
        })
        return {
            "persona_id": persona_id,
            "run_id": manifest["run_id"],
            "reference_dir": str(destination),
            "manifest_path": str(canonical_path),
            "file_count": len(promoted),
            "mean_identity_score": manifest["mean_identity_score"],
            "minimum_identity_score": manifest["minimum_identity_score"],
        }
