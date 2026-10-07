"""Normalization layer converting heterogeneous platform metrics into standard schema."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _timestamp(payload: Dict[str, Any]) -> str:
    """Retain the observation's fetch time rather than the time of normalization."""
    return payload.get("fetched_at") or payload.get("timestamp") or datetime.now(timezone.utc).isoformat()


def _counter(value: Any) -> int:
    """Accept whole counters without silently truncating or accepting negative values."""
    if isinstance(value, bool):
        raise ValueError("Metric counters must be nonnegative integers")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Metric counters must be nonnegative integers") from exc
    if result < 0 or (not isinstance(value, str) and result != value):
        raise ValueError("Metric counters must be nonnegative integers")
    return result


@dataclass
class NormalizedMetrics:
    """A fetched observation; counters are cumulative unless explicitly declared otherwise.

    Monetary fields are retained for explicitly supplied manual bookkeeping. Social
    observations do not establish authenticated purchases and should leave them zero.
    """
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
    cumulative: bool = True

    def __post_init__(self):
        if not self.external_id:
            # Precise time plus values permit updated observations in the same hour,
            # including vendors that return multiple snapshots with one timestamp.
            observation = asdict(self)
            observation.pop("external_id")
            fingerprint = hashlib.sha256(
                json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            self.external_id = f"met_{self.platform}_{self.post_id}_{fingerprint}"

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
        """Normalize Meta Insights; money arguments are explicit manual bookkeeping only."""
        data_items = raw_payload.get("data", [])
        metric_map = {}
        for item in data_items:
            name = item.get("name")
            values = item.get("values") or []
            val = values[0].get("value", 0) if values else item.get("total_value", {}).get("value", 0)
            metric_map[name] = val

        impressions = _counter(metric_map.get("impressions", raw_payload.get("impressions", 0)))
        views = _counter(metric_map.get("views", metric_map.get("plays", raw_payload.get("views", 0))))
        likes = _counter(metric_map.get("likes", raw_payload.get("likes", 0)))
        comments = _counter(metric_map.get("comments", raw_payload.get("comments", 0)))
        shares = _counter(metric_map.get("shares", raw_payload.get("shares", 0)))
        saves = _counter(metric_map.get("saved", raw_payload.get("saves", 0)))
        profile_visits = _counter(metric_map.get("profile_activity", raw_payload.get("profile_visits", 0)))
        link_clicks = _counter(metric_map.get("website_clicks", raw_payload.get("link_clicks", 0)))

        watch_ms = _counter(raw_payload.get("watch_time_ms", 0))
        completion_rate = float(raw_payload.get("completion_rate", 0.0))

        return NormalizedMetrics(
            platform="instagram",
            post_id=post_id,
            candidate_id=candidate_id,
            persona_id=persona_id,
            timestamp=_timestamp(raw_payload),
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
            revenue_cents=_counter(revenue_cents),
            cost_cents=_counter(cost_cents),
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
        """Normalize fetched social counters; money arguments are manual bookkeeping only."""
        d = metrics_obj if isinstance(metrics_obj, dict) else metrics_obj.to_dict()

        return NormalizedMetrics(
            platform=platform,
            post_id=post_id,
            candidate_id=candidate_id,
            persona_id=persona_id,
            timestamp=_timestamp(d),
            impressions=_counter(d.get("impressions", 0)),
            views=_counter(d.get("views", 0)),
            watch_time_ms=_counter(d.get("watch_time_ms", 0)),
            completion_rate=float(d.get("completion_rate", 0.0)),
            likes=_counter(d.get("likes", 0)),
            comments=_counter(d.get("comments", 0)),
            shares=_counter(d.get("shares", 0)),
            saves=_counter(d.get("saves", 0)),
            profile_visits=_counter(d.get("profile_visits", 0)),
            link_clicks=_counter(d.get("link_clicks", 0)),
            revenue_cents=_counter(revenue_cents),
            cost_cents=_counter(cost_cents),
        )
