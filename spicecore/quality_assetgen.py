"""Production asset generation with visual quality gating layered over AssetGenerator."""

from __future__ import annotations

import json
from pathlib import Path

from .assetgen import AssetGenerator
from .quality import QualityGate


class QualityAssetGenerator:
    def __init__(self, asset_generator: AssetGenerator, quality_threshold: float = 0.78):
        self.asset_generator = asset_generator
        self.store = asset_generator.store
        self.provider = asset_generator.provider
        self.quality_gate = QualityGate(self.provider, threshold=quality_threshold)

    def generate(self, *args, **kwargs) -> dict:
        result = self.asset_generator.generate(*args, **kwargs)
        image_bytes = Path(result["asset_path"]).read_bytes()
        meta_path = Path(result["metadata_path"])
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        quality = self.quality_gate.score(
            image_bytes,
            metadata["mime_type"],
            metadata.get("channel", ""),
        )

        candidate_id = result["candidate_id"]
        current = self.store.candidate(candidate_id)
        if current["status"] == "proposed" and not quality["passed"]:
            note = (
                f"quality score {quality['score']:.4f} below {quality['threshold']:.4f}; "
                f"reasons={','.join(quality['reasons']) or 'overall'}"
            )
            self.store.review(
                candidate_id,
                "rejected",
                reviewer="quality-gate",
                note=note,
            )

        final_status = self.store.candidate(candidate_id)["status"]
        metadata["quality"] = quality
        metadata["status"] = final_status
        meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        self.store.record_event("quality_checked", {
            "candidate_id": candidate_id,
            "asset_id": result["asset_id"],
            "persona_id": metadata["persona_id"],
            **quality,
            "final_status": final_status,
        })

        return {
            **result,
            "quality": quality,
            "status": final_status,
        }

    def batch(self, personas: list[dict], theme: str, channel: str, offer: str,
              count_per_persona: int = 1, seed: int | None = None,
              width: int = 768, height: int = 1024, cost_cents: int = 0) -> list[dict]:
        if count_per_persona < 1 or count_per_persona > 20:
            raise ValueError("count_per_persona must be 1..20")
        output = []
        for p_index, persona in enumerate(personas):
            for variant in range(count_per_persona):
                derived_seed = None if seed is None else seed + p_index * 1000 + variant
                output.append(self.generate(
                    persona=persona,
                    theme=theme,
                    channel=channel,
                    offer=offer,
                    seed=derived_seed,
                    width=width,
                    height=height,
                    cost_cents=cost_cents,
                ))
        return output
