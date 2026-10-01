"""Deterministic scene builder for multi-clip short-form video generation."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SceneSpec:
    id: str
    duration_seconds: float
    source_asset_uri: str
    dialogue: str
    motion: str = "subtle push-in"  # subtle push-in, pan left, hand interaction, static close-up
    transition: str = "fade"  # fade, cut, dissolve
    camera_angle: str = "medium"
    order: int = 0
    estimated_cost_cents: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneSpec":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            duration_seconds=float(data.get("duration_seconds", 5.0)),
            source_asset_uri=data.get("source_asset_uri", data.get("source_asset", "")),
            dialogue=data.get("dialogue", ""),
            motion=data.get("motion", "subtle push-in"),
            transition=data.get("transition", "fade"),
            camera_angle=data.get("camera_angle", "medium"),
            order=int(data.get("order", 0)),
            estimated_cost_cents=int(data.get("estimated_cost_cents", 10)),
        )


@dataclass
class RenderPlan:
    plan_id: str
    persona_id: str
    candidate_id: str
    aspect_ratio: str
    total_duration_seconds: float
    scenes: List[SceneSpec]
    full_script: str
    estimated_total_cost_cents: int
    soundtrack: Optional[str] = None
    cta: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "persona_id": self.persona_id,
            "candidate_id": self.candidate_id,
            "aspect_ratio": self.aspect_ratio,
            "total_duration_seconds": self.total_duration_seconds,
            "scenes": [s.to_dict() for s in self.scenes],
            "full_script": self.full_script,
            "estimated_total_cost_cents": self.estimated_total_cost_cents,
            "soundtrack": self.soundtrack,
            "cta": self.cta,
            "created_at": self.created_at,
        }


class SceneBuilder:
    """Assembles short clips into a final short-form video render plan."""

    def __init__(
        self,
        default_aspect_ratio: str = "9:16",
        min_scene_duration: float = 3.0,
        max_scene_duration: float = 8.0,
    ):
        self.default_aspect_ratio = default_aspect_ratio
        self.min_scene_duration = min_scene_duration
        self.max_scene_duration = max_scene_duration

    def build_standard_plan(
        self,
        persona_id: str,
        candidate_id: str,
        source_asset_uri: str,
        script: str,
        offer: Optional[str] = None,
        cta: Optional[str] = None,
        soundtrack: Optional[str] = None,
        aspect_ratio: str = "9:16",
    ) -> RenderPlan:
        """Constructs a standard 3-scene sequence (Hook/Intro -> Core/Product -> CTA) from a single approved asset and script."""
        sentences = [s.strip() for s in script.split(".") if s.strip()]
        if not sentences:
            sentences = [script.strip()]

        intro_text = sentences[0] if len(sentences) >= 1 else script
        core_text = sentences[1] if len(sentences) >= 2 else (sentences[0] if len(sentences) == 1 else "")
        cta_text = cta or (sentences[2] if len(sentences) >= 3 else f"Tap link for {offer or 'exclusive access'}.")

        scenes = [
            SceneSpec(
                id="intro",
                order=1,
                duration_seconds=5.0,
                source_asset_uri=source_asset_uri,
                dialogue=intro_text,
                motion="subtle push-in",
                camera_angle="medium close-up",
                estimated_cost_cents=10,
            ),
            SceneSpec(
                id="product",
                order=2,
                duration_seconds=6.0,
                source_asset_uri=source_asset_uri,
                dialogue=core_text,
                motion="hand interaction",
                camera_angle="close-up",
                estimated_cost_cents=10,
            ),
            SceneSpec(
                id="cta",
                order=3,
                duration_seconds=5.0,
                source_asset_uri=source_asset_uri,
                dialogue=cta_text,
                motion="static close-up",
                camera_angle="direct address",
                estimated_cost_cents=10,
            ),
        ]

        total_duration = sum(s.duration_seconds for s in scenes)
        full_script = " ".join(s.dialogue for s in scenes if s.dialogue)
        est_cost = sum(s.estimated_cost_cents for s in scenes) + 15  # scenes + voice + assembly

        return RenderPlan(
            plan_id=str(uuid.uuid4()),
            persona_id=persona_id,
            candidate_id=candidate_id,
            aspect_ratio=aspect_ratio or self.default_aspect_ratio,
            total_duration_seconds=total_duration,
            scenes=scenes,
            full_script=full_script,
            estimated_total_cost_cents=est_cost,
            soundtrack=soundtrack,
            cta=cta_text,
        )

    def parse_spec(
        self,
        persona_id: str,
        candidate_id: str,
        spec: Dict[str, Any],
    ) -> RenderPlan:
        """Parses a structured YAML/Dict scene specification."""
        raw_scenes = spec.get("scenes", [])
        scenes: List[SceneSpec] = []
        for idx, s in enumerate(raw_scenes, start=1):
            scene = SceneSpec.from_dict(s)
            scene.order = s.get("order", idx)
            # Enforce duration bounds
            scene.duration_seconds = max(
                self.min_scene_duration,
                min(scene.duration_seconds, self.max_scene_duration),
            )
            scenes.append(scene)

        total_duration = sum(s.duration_seconds for s in scenes)
        full_script = " ".join(s.dialogue for s in scenes if s.dialogue)
        est_cost = sum(s.estimated_cost_cents for s in scenes)

        return RenderPlan(
            plan_id=spec.get("plan_id", str(uuid.uuid4())),
            persona_id=persona_id,
            candidate_id=candidate_id,
            aspect_ratio=spec.get("aspect_ratio", self.default_aspect_ratio),
            total_duration_seconds=total_duration,
            scenes=scenes,
            full_script=full_script,
            estimated_total_cost_cents=est_cost,
            soundtrack=spec.get("soundtrack"),
            cta=spec.get("cta"),
        )
