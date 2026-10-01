"""Base interfaces for social platform publishers and scheduling adapters."""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class PublishResult:
    success: bool
    platform: str
    external_post_id: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    response_metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retryable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlatformMetrics:
    platform: str
    post_id: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
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
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Publisher(abc.ABC):
    """Abstract interface for social publishing networks."""

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        pass

    @abc.abstractmethod
    def publish(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        idempotency_key: Optional[str] = None,
        hashtags: Optional[list] = None,
        **kwargs,
    ) -> PublishResult:
        """Publishes media to the target platform idempotently."""
        pass

    @abc.abstractmethod
    def schedule(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        scheduled_at_iso: str,
        idempotency_key: Optional[str] = None,
        **kwargs,
    ) -> PublishResult:
        """Schedules media using native platform scheduling API if supported."""
        pass

    @abc.abstractmethod
    def delete(self, external_post_id: str, account_id: str) -> bool:
        """Deletes a previously published post."""
        pass

    @abc.abstractmethod
    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        """Retrieves raw performance metrics for a published post."""
        pass
