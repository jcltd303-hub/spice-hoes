"""Normalization layer converting heterogeneous platform metrics into standard schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class NormalizedMetrics:
    platform: str
    post_id: str
    candidate_id: str
    persona_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    impressions: int = 0
    views: int = 0
    watch_time_ms: int = 0
    completion_rate: float = 0.0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    profile_visits: int = 0
    link_clicks: int = 0
    revenue_cents: int = 0
    cost_cents: int = 0
    external_id: Optional[str] = None

    def __post_init__(self):
        if not self.external_id:
            # Deterministic idempotent key per post + timestamp hour
            hour_stamp = self.timestamp[:13]
            self.external_id = f"met_{self.platform}_{self.post_id}_{hour_stamp}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedMetrics":
        return cls(**data)


class MetricsNormalizer:
    """Normalizes vendor-specific analytics payloads into the unified schema."""

    @staticmethod
    def normalize_instagram(
        raw_payload: Dict[str, Any],
        candidate_id: str,
        persona_id: str,
        post_id: str,
        cost_cents: int = 0,
        revenue_cents: int = 0,
    ) -> NormalizedMetrics:
        """Normalizes Meta Instagram Insights response."""
        data_items = raw_payload.get("data", [])
        metric_map = {}
        for item in data_items:
            name = item.get("name")
            val = item.get("values", [{}])[0].get("value", 0)
            metric_map[name] = val

        impressions = int(metric_map.get("impressions", raw_payload.get("impressions", 0)))
        views = int(metric_map.get("plays", raw_payload.get("views", 0)))
        likes = int(metric_map.get("likes", raw_payload.get("likes", 0)))
        comments = int(metric_map.get("comments", raw_payload.get("comments", 0)))
        shares = int(metric_map.get("shares", raw_payload.get("shares", 0)))
        saves = int(metric_map.get("saved", raw_payload.get("saves", 0)))
        profile_visits = int(metric_map.get("profile_activity", raw_payload.get("profile_visits", 0)))
        link_clicks = int(metric_map.get("website_clicks", raw_payload.get("link_clicks", 0)))

        watch_ms = int(raw_payload.get("watch_time_ms", views * 6500))
        completion_rate = float(raw_payload.get("completion_rate", 0.65 if views > 0 else 0.0))

        return NormalizedMetrics(
            platform="instagram",
            post_id=post_id,
            candidate_id=candidate_id,
            persona_id=persona_id,
            impressions=impressions,
            views=views,
            watch_time_ms=watch_ms,
            completion_rate=completion_rate,
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            profile_visits=profile_visits,
            link_clicks=link_clicks,
            revenue_cents=revenue_cents,
            cost_cents=cost_cents,
            external_id=f"met_ig_{post_id}",
        )

    @staticmethod
    def normalize_generic(
        platform: str,
        metrics_obj: Any,
        candidate_id: str,
        persona_id: str,
        post_id: str,
        cost_cents: int = 0,
        revenue_cents: int = 0,
    ) -> NormalizedMetrics:
        """Normalizes PlatformMetrics object or generic dictionary."""
        d = metrics_obj if isinstance(metrics_obj, dict) else metrics_obj.to_dict()

        return NormalizedMetrics(
            platform=platform,
            post_id=post_id,
            candidate_id=candidate_id,
            persona_id=persona_id,
            impressions=int(d.get("impressions", 0)),
            views=int(d.get("views", 0)),
            watch_time_ms=int(d.get("watch_time_ms", 0)),
            completion_rate=float(d.get("completion_rate", 0.0)),
            likes=int(d.get("likes", 0)),
            comments=int(d.get("comments", 0)),
            shares=int(d.get("shares", 0)),
            saves=int(d.get("saves", 0)),
            profile_visits=int(d.get("profile_visits", 0)),
            link_clicks=int(d.get("link_clicks", 0)),
            revenue_cents=revenue_cents,
            cost_cents=cost_cents,
            external_id=f"met_{platform}_{post_id}",
        )
