"""In-memory mock publisher for unit tests and local workflow verification."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import PlatformMetrics, Publisher, PublishResult


class MockPublisher(Publisher):
    """In-memory test publisher with strict idempotency verification and failure simulation."""

    def __init__(self, platform: str = "mock_social", fail_next: bool = False, retryable_failure: bool = True):
        self._platform = platform
        self.published_posts: Dict[str, Dict[str, Any]] = {}
        self.idempotency_map: Dict[str, str] = {}  # idempotency_key -> external_post_id
        self.fail_next = fail_next
        self.retryable_failure = retryable_failure
        self.publish_call_count = 0

    @property
    def platform_name(self) -> str:
        return self._platform

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
        self.publish_call_count += 1

        # Check idempotency: if already processed, return existing result without re-publishing
        if idempotency_key and idempotency_key in self.idempotency_map:
            post_id = self.idempotency_map[idempotency_key]
            post = self.published_posts[post_id]
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_post_id=post_id,
                canonical_url=post["canonical_url"],
                published_at=post["published_at"],
                response_metadata={"idempotent_replay": True, "call_count": self.publish_call_count},
            )

        # Failure simulation
        if self.fail_next:
            self.fail_next = False
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error_message="Simulated upstream network timeout (504)",
                retryable=self.retryable_failure,
            )

        post_id = f"mock_post_{uuid.uuid4().hex[:12]}"
        canonical_url = f"https://mock.social/@{account_id}/p/{post_id}"
        now_iso = datetime.now(timezone.utc).isoformat()

        post_record = {
            "post_id": post_id,
            "media_uri": media_uri,
            "caption": caption,
            "disclosure": disclosure,
            "account_id": account_id,
            "canonical_url": canonical_url,
            "published_at": now_iso,
            "hashtags": hashtags or [],
            "idempotency_key": idempotency_key,
        }
        self.published_posts[post_id] = post_record

        if idempotency_key:
            self.idempotency_map[idempotency_key] = post_id

        return PublishResult(
            success=True,
            platform=self.platform_name,
            external_post_id=post_id,
            canonical_url=canonical_url,
            published_at=now_iso,
            response_metadata={"status": "published", "call_count": self.publish_call_count},
        )

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
        return self.publish(
            media_uri=media_uri,
            caption=caption,
            disclosure=disclosure,
            account_id=account_id,
            idempotency_key=idempotency_key,
            **kwargs,
        )

    def delete(self, external_post_id: str, account_id: str) -> bool:
        if external_post_id in self.published_posts:
            del self.published_posts[external_post_id]
            return True
        return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if external_post_id not in self.published_posts:
            raise KeyError(f"Post {external_post_id} not found on {self.platform_name}")

        return PlatformMetrics(
            platform=self.platform_name,
            post_id=external_post_id,
            impressions=1250,
            views=980,
            watch_time_ms=8820000,
            completion_rate=0.68,
            likes=142,
            comments=18,
            shares=12,
            saves=34,
            profile_visits=28,
            link_clicks=15,
            raw_payload={"mock": True, "source": "simulated_metrics"},
        )
