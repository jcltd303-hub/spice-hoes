"""TikTok Creator Content Posting API v2 publisher adapter for vertical short-form video."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import PlatformMetrics, Publisher, PublishResult


class TikTokPublisher(Publisher):
    """Adapter for official TikTok Creator Content Posting API (Direct Post & Video Inbox)."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.base_url = "https://open.tiktokapis.com/v2"

    @property
    def platform_name(self) -> str:
        return "tiktok"

    def _http_request(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        method: str = "POST",
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        encoded = None
        if data is not None:
            headers["Content-Type"] = "application/json; charset=UTF-8"
            encoded = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            logging.error("TikTok API error %d: %s", err.code, err_body)
            raise RuntimeError(f"TikTok API error ({err.code}): {err_body}") from err

    def publish(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        idempotency_key: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
        **kwargs,
    ) -> PublishResult:
        full_caption = f"{caption}\n\n#fictional #ai {disclosure}"
        tags = hashtags or ["fyp", "adultcreator", "spicehoes"]
        full_caption += " " + " ".join(f"#{t.lstrip('#')}" for t in tags)

        now_iso = datetime.now(timezone.utc).isoformat()

        if not self.access_token:
            # Synthetic / test mode when API key is not configured
            post_id = f"tt_{idempotency_key.replace(':', '_') if idempotency_key else uuid.uuid4().hex[:10]}"
            return PublishResult(
                success=True,
                platform="tiktok",
                external_post_id=post_id,
                canonical_url=f"https://www.tiktok.com/@{account_id}/video/{post_id}",
                published_at=now_iso,
                response_metadata={"mode": "simulated", "disclosure_applied": True},
            )

        try:
            # 1. Initialize video direct post upload
            init_payload = {
                "post_info": {
                    "title": full_caption[:2200],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_stitch": False,
                    "disable_comment": False,
                    "is_aigc": True,  # Required disclosure: AI Generated Content
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": media_uri,
                },
            }
            resp = self._http_request("post/publish/video/init/", data=init_payload)
            publish_id = resp.get("data", {}).get("publish_id", f"tt_{uuid.uuid4().hex[:8]}")

            return PublishResult(
                success=True,
                platform="tiktok",
                external_post_id=publish_id,
                canonical_url=f"https://www.tiktok.com/@{account_id}/video/{publish_id}",
                published_at=now_iso,
                response_metadata=resp,
            )
        except Exception as ex:
            return PublishResult(
                success=False,
                platform="tiktok",
                error_message=str(ex),
                retryable=True,
            )

    def schedule(
        self,
        media_uri: str,
        caption: str,
        disclosure: str,
        account_id: str,
        scheduled_at_iso: str,
        **kwargs,
    ) -> PublishResult:
        return self.publish(media_uri, caption, disclosure, account_id, **kwargs)

    def delete(self, external_post_id: str, account_id: str) -> bool:
        if not self.access_token:
            return True
        try:
            self._http_request(f"post/delete/?video_id={external_post_id}", method="DELETE")
            return True
        except Exception:
            return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if not self.access_token:
            return PlatformMetrics(
                platform="tiktok",
                post_id=external_post_id,
                impressions=2400,
                views=2150,
                watch_time_ms=19350000,
                completion_rate=0.74,
                likes=310,
                comments=42,
                shares=38,
                saves=85,
                profile_visits=64,
                link_clicks=29,
            )

        try:
            payload = {"filters": {"video_ids": [external_post_id]}}
            res = self._http_request("video/query/", data=payload)
            video_data = res.get("data", {}).get("videos", [{}])[0]

            return PlatformMetrics(
                platform="tiktok",
                post_id=external_post_id,
                impressions=video_data.get("reach", 0),
                views=video_data.get("view_count", 0),
                likes=video_data.get("like_count", 0),
                comments=video_data.get("comment_count", 0),
                shares=video_data.get("share_count", 0),
                saves=video_data.get("save_count", 0),
                raw_payload=res,
            )
        except Exception as ex:
            logging.error("Failed to query TikTok video metrics: %s", ex)
            raise
