"""YouTube Data API v3 publisher adapter specifically configured for vertical YouTube Shorts."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import PlatformMetrics, Publisher, PublishResult


class YouTubeShortsPublisher(Publisher):
    """Adapter for publishing vertical 9:16 videos as YouTube Shorts via YouTube Data API v3."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("YOUTUBE_ACCESS_TOKEN", "")
        self.upload_url = "https://www.googleapis.com/upload/youtube/v3/videos"
        self.api_url = "https://www.googleapis.com/youtube/v3"

    @property
    def platform_name(self) -> str:
        return "youtube_shorts"

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
        # YouTube Shorts requires #Shorts in title or description for vertical shelf discovery
        title = f"{caption[:70]} #Shorts"
        full_description = f"{caption}\n\n#Shorts #SpiceHoes #AIInfluencer\n\n{disclosure}"
        tags = hashtags or ["Shorts", "SpiceHoes", "AdultCreator"]

        now_iso = datetime.now(timezone.utc).isoformat()

        if not self.access_token:
            return PublishResult(
                success=False,
                platform="youtube_shorts",
                error_message="YOUTUBE_ACCESS_TOKEN is not configured",
                retryable=False,
            )

        try:
            # Multi-part or resumable upload metadata
            metadata = {
                "snippet": {
                    "title": title,
                    "description": full_description,
                    "tags": tags,
                    "categoryId": "24",  # Entertainment
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,  # Mandatory adult creator declaration
                },
            }

            url = f"{self.upload_url}?uploadType=multipart&part=snippet,status"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            }
            req = urllib.request.Request(url, data=json.dumps(metadata).encode("utf-8"), headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=45) as resp:
                result_data = json.loads(resp.read().decode("utf-8"))
                video_id = result_data["id"]
                canonical_url = f"https://www.youtube.com/shorts/{video_id}"

                return PublishResult(
                    success=True,
                    platform="youtube_shorts",
                    external_post_id=video_id,
                    canonical_url=canonical_url,
                    published_at=now_iso,
                    response_metadata=result_data,
                )

        except Exception as ex:
            logging.error("YouTube Shorts upload error: %s", ex)
            return PublishResult(
                success=False,
                platform="youtube_shorts",
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
            return False
        try:
            url = f"{self.api_url}/videos?id={external_post_id}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            req = urllib.request.Request(url, headers=headers, method="DELETE")
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if not self.access_token:
            raise RuntimeError("YOUTUBE_ACCESS_TOKEN is not configured")

        try:
            url = f"{self.api_url}/videos?id={external_post_id}&part=statistics"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                item = data.get("items", [{}])[0]
                stats = item.get("statistics", {})

                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))

                return PlatformMetrics(
                    platform="youtube_shorts",
                    post_id=external_post_id,
                    impressions=views * 2,
                    views=views,
                    likes=likes,
                    comments=comments,
                    raw_payload=data,
                )
        except Exception as ex:
            logging.error("YouTube statistics fetch failed: %s", ex)
            raise
