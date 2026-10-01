"""Normalized media and render job abstractions for short-form video generation."""

from __future__ import annotations

import enum
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RenderState(str, enum.Enum):
    PLANNED = "planned"
    RENDERING = "rendering"
    RENDERED = "rendered"
    QA_PASSED = "qa_passed"
    REVIEW_READY = "review_ready"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"

    # Failure / Terminal States
    RENDER_FAILED = "render_failed"
    QA_FAILED = "qa_failed"
    PUBLISH_FAILED = "publish_failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    REVISE = "revise"


# Alias for compatibility
MediaJobStatus = RenderState


@dataclass
class CostBreakdown:
    image_generation_cents: int = 0
    video_generation_cents: int = 0
    voice_generation_cents: int = 0
    lipsync_cents: int = 0
    render_cents: int = 0
    distribution_cents: int = 0

    @property
    def total_cents(self) -> int:
        return (
            self.image_generation_cents
            + self.video_generation_cents
            + self.voice_generation_cents
            + self.lipsync_cents
            + self.render_cents
            + self.distribution_cents
        )

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CostBreakdown":
        return cls(
            image_generation_cents=int(data.get("image_generation_cents", 0)),
            video_generation_cents=int(data.get("video_generation_cents", 0)),
            voice_generation_cents=int(data.get("voice_generation_cents", 0)),
            lipsync_cents=int(data.get("lipsync_cents", 0)),
            render_cents=int(data.get("render_cents", 0)),
            distribution_cents=int(data.get("distribution_cents", 0)),
        )


@dataclass
class QAReport:
    passed: bool
    score: float
    checks: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QAReport":
        return cls(
            passed=bool(data.get("passed", False)),
            score=float(data.get("score", 0.0)),
            checks=dict(data.get("checks", {})),
            details=dict(data.get("details", {})),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class MediaJob:
    """Normalized media generation job matching section 1 of specification."""

    persona_id: str
    candidate_id: str
    source_asset_uri: str
    script: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    voice_profile: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 15.0
    aspect_ratio: str = "9:16"
    captions: List[Dict[str, Any]] = field(default_factory=list)
    soundtrack: Optional[str] = None
    cta: Optional[str] = None
    offer: Optional[str] = None
    product_id: Optional[str] = None

    # Providers
    video_provider: str = "mock"
    voice_provider: str = "mock"
    lipsync_provider: str = "mock"

    # Cost tracking (separated into itemized breakdown)
    generation_cost_cents: int = 0
    render_cost_cents: int = 0
    costs: CostBreakdown = field(default_factory=CostBreakdown)

    # State Machine
    status: RenderState = RenderState.PLANNED
    output_uri: Optional[str] = None
    thumbnail_uri: Optional[str] = None
    qa_report: Optional[QAReport] = None

    # Review fields
    reviewer: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_at: Optional[str] = None

    # Metadata & Provenance
    provenance: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0

    # Timestamps
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def update_status(
        self, new_status: RenderState, error_message: Optional[str] = None
    ) -> None:
        self.status = new_status
        if error_message:
            self.error_message = error_message
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def sync_costs(self) -> None:
        self.generation_cost_cents = (
            self.costs.image_generation_cents
            + self.costs.video_generation_cents
            + self.costs.voice_generation_cents
            + self.costs.lipsync_cents
        )
        self.render_cost_cents = self.costs.render_cents

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = (
            self.status.value
            if isinstance(self.status, RenderState)
            else str(self.status)
        )
        if self.qa_report:
            data["qa_report"] = self.qa_report.to_dict()
        data["costs"] = self.costs.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaJob":
        costs_data = data.get("costs", {})
        qa_data = data.get("qa_report")

        status_val = data.get("status", RenderState.PLANNED)
        if isinstance(status_val, str):
            status = RenderState(status_val)
        else:
            status = status_val

        job = cls(
            id=data.get("id", str(uuid.uuid4())),
            persona_id=data["persona_id"],
            candidate_id=data["candidate_id"],
            source_asset_uri=data["source_asset_uri"],
            script=data["script"],
            voice_profile=data.get("voice_profile", {}),
            duration_seconds=float(data.get("duration_seconds", 15.0)),
            aspect_ratio=data.get("aspect_ratio", "9:16"),
            captions=data.get("captions", []),
            soundtrack=data.get("soundtrack"),
            cta=data.get("cta"),
            offer=data.get("offer"),
            product_id=data.get("product_id"),
            video_provider=data.get("video_provider", "mock"),
            voice_provider=data.get("voice_provider", "mock"),
            lipsync_provider=data.get("lipsync_provider", "mock"),
            generation_cost_cents=int(data.get("generation_cost_cents", 0)),
            render_cost_cents=int(data.get("render_cost_cents", 0)),
            costs=CostBreakdown.from_dict(costs_data)
            if costs_data
            else CostBreakdown(),
            status=status,
            output_uri=data.get("output_uri"),
            thumbnail_uri=data.get("thumbnail_uri"),
            qa_report=QAReport.from_dict(qa_data) if qa_data else None,
            reviewer=data.get("reviewer"),
            review_note=data.get("review_note"),
            reviewed_at=data.get("reviewed_at"),
            provenance=data.get("provenance", {}),
            error_message=data.get("error_message"),
            retry_count=int(data.get("retry_count", 0)),
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            updated_at=data.get(
                "updated_at", datetime.now(timezone.utc).isoformat()
            ),
        )
        job.sync_costs()
        return job


# RenderJob is an alias for MediaJob
RenderJob = MediaJob
