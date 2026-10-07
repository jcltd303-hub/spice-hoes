"""TikTok Direct Post adapter with persisted asynchronous publication state."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from .base import (
    PublisherValidationError, safe_provider_error,
    PlatformMetrics, Publisher, PublisherAPIError, PublishResult,
    failed_publish_result, pending_publish_result, require_public_media_url,
    resume_provider_state,
)


class TikTokPublisher(Publisher):
    """Official Direct Post API; URL pulls need a TikTok-verified domain.

    Protocol: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
    Status: https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status
    The creator must select a privacy level; unaudited clients cannot post publicly.
    """

    def __init__(self, access_token: Optional[str] = None, privacy_level: Optional[str] = None):
        self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "") if access_token is None else access_token
        self.privacy_level = os.getenv("TIKTOK_PRIVACY_LEVEL", "") if privacy_level is None else privacy_level
        self.base_url = "https://open.tiktokapis.com/v2"

    @property
    def platform_name(self) -> str:
        return "tiktok"

    def _http_request(self, endpoint: str, data: Optional[Dict[str, Any]] = None, method: str = "POST") -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        encoded = None
        if data is not None:
            if method == "GET":
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(data)
            else:
                headers["Content-Type"] = "application/json; charset=UTF-8"
                encoded = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error", {})
            except (ValueError, UnicodeDecodeError):
                detail = {}
            raise PublisherAPIError(
                safe_provider_error(self.platform_name, code=detail.get('code', error.code)),
                retryable=error.code == 429 or error.code >= 500,
                ambiguous=error.code >= 500,
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict) or not payload["error"].get("code"):
            raise PublisherValidationError("TikTok returned a malformed response without error.code")
        detail = payload["error"]
        if detail["code"] != "ok":
            raise PublisherAPIError(
                safe_provider_error(self.platform_name, code=detail['code']),
                retryable=detail["code"] in ("rate_limit_exceeded", "internal_error"),
            )
        return payload

    def publish(
        self, media_uri: str, caption: str, disclosure: str, account_id: str,
        idempotency_key: Optional[str] = None, hashtags: Optional[List[str]] = None,
        resume_metadata: Optional[Dict[str, Any]] = None, **kwargs,
    ) -> PublishResult:
        if not self.access_token:
            return failed_publish_result(self.platform_name, "TIKTOK_ACCESS_TOKEN is not configured")
        state: Dict[str, Any] = {}
        operation = "validate"
        try:
            state = resume_provider_state(resume_metadata, self.platform_name, account_id)
            if state:
                if state.get("phase") == "initialization_unknown":
                    return failed_publish_result(self.platform_name, "TikTok initialization outcome requires reconciliation before another submission", state, needs_reconciliation=True)
                if not state.get("publish_id"):
                    raise PublisherValidationError("TikTok provider state lacks a publish_id")
            else:
                require_public_media_url(media_uri)
                suffix = PurePosixPath(urllib.parse.urlsplit(media_uri).path).suffix.lower()
                if suffix and suffix not in (".mp4", ".mov", ".webm"):
                    raise PublisherValidationError("TikTok video publishing requires MP4, MOV, or WebM media")
                privacy = kwargs.get("privacy_level") or self.privacy_level
                if not privacy:
                    raise PublisherValidationError("TikTok requires an explicitly selected privacy_level or TIKTOK_PRIVACY_LEVEL")
                full_caption = "\n\n".join(text for text in (caption, f"#fictional #ai {disclosure}".strip()) if text)
                if hashtags:
                    full_caption += " " + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
                if len(full_caption.encode("utf-16-le")) // 2 > 2200:
                    raise PublisherValidationError("TikTok caption exceeds 2,200 UTF-16 characters; shorten it before publishing")
                if not account_id:
                    raise PublisherValidationError("TikTok account_id is required")
                operation = "creator_info"
                creator_response = self._http_request("post/publish/creator_info/query/", data={})
                creator = creator_response.get("data", {})
                if str(creator.get("creator_username", "")).lstrip("@").casefold() != account_id.lstrip("@").casefold():
                    raise PublisherValidationError("TikTok account_id must match the authorized creator_username")
                if privacy not in creator.get("privacy_level_options", []):
                    raise PublisherValidationError("Selected TikTok privacy level is not available in the creator's current privacy options")
                duration = kwargs.get("duration_seconds")
                maximum = creator.get("max_video_post_duration_sec")
                if duration is not None and (not math.isfinite(float(duration)) or float(duration) <= 0 or maximum is None or float(duration) > float(maximum)):
                    raise PublisherValidationError(f"TikTok video duration exceeds the creator's permitted limit ({maximum} seconds)")
                post_info = {
                    "title": full_caption,
                    "privacy_level": privacy,
                    "disable_duet": bool(creator.get("duet_disabled")) or bool(kwargs.get("disable_duet", False)),
                    "disable_stitch": bool(creator.get("stitch_disabled")) or bool(kwargs.get("disable_stitch", False)),
                    "disable_comment": bool(creator.get("comment_disabled")) or bool(kwargs.get("disable_comment", False)),
                    "brand_content_toggle": bool(kwargs.get("brand_content_toggle", False)),
                    "brand_organic_toggle": bool(kwargs.get("brand_organic_toggle", False)),
                    "is_aigc": True,
                }
                state = {"platform": self.platform_name, "account_id": account_id, "privacy_level": privacy}
                operation = "initialize"
                response = self._http_request("post/publish/video/init/", data={"post_info": post_info, "source_info": {"source": "PULL_FROM_URL", "video_url": media_uri}})
                publish_id = response.get("data", {}).get("publish_id")
                if not publish_id:
                    raise PublisherValidationError("TikTok initialization succeeded without returning a publish_id")
                state.update(publish_id=str(publish_id), phase="processing")
                return pending_publish_result(self.platform_name, state, response)

            if not state.get("post_ids"):
                operation = "status"
                response = self._http_request("post/publish/status/fetch/", data={"publish_id": state["publish_id"]})
                data = response.get("data", {})
                status = data.get("status")
                state["status"] = status
                if status == "FAILED":
                    reason = str(data.get("fail_reason", "Unknown provider failure"))
                    # Retain the failed job: retrying a status query cannot repair it.
                    state["phase"] = "failed"
                    return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, code=reason), state)
                if status not in ("PUBLISH_COMPLETE", "POST_PUBLISH_COMPLETE"):
                    return pending_publish_result(self.platform_name, state, response)
                # The misspelling is the documented API field, not a publish_id.
                post_ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
                if not isinstance(post_ids, list) or not post_ids:
                    state["phase"] = "awaiting_public_post_id"
                    return pending_publish_result(self.platform_name, state, response, "TikTok completed the job but has not returned a public post ID")
                state.update(post_ids=[str(post_id) for post_id in post_ids], phase="published")

            operation = "verify_url"
            video_id = state["post_ids"][0]
            response = self._query_video(video_id, "id,share_url,create_time")
            video = next((video for video in response.get("data", {}).get("videos", []) if str(video.get("id")) == video_id), None)
            if not video or not video.get("share_url"):
                return pending_publish_result(self.platform_name, state, response, "TikTok post exists; waiting for an API-verified share URL")
            share_url = video["share_url"]
            parsed = urllib.parse.urlsplit(share_url)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not (host == "tiktok.com" or host.endswith(".tiktok.com")) or parsed.username or parsed.password:
                return failed_publish_result(self.platform_name, "TikTok returned an invalid share URL", state, needs_reconciliation=True)
            published_at = None
            if video.get("create_time") is not None:
                published_at = datetime.fromtimestamp(int(video["create_time"]), timezone.utc).isoformat()
            return PublishResult(
                success=True, platform=self.platform_name, external_post_id=video_id,
                canonical_url=share_url, published_at=published_at,
                response_metadata={"provider_state": state, "response": response},
            )
        except Exception as error:
            rejected = isinstance(error, PublisherAPIError) and not error.ambiguous
            if operation == "initialize" and not rejected:
                state["phase"] = "initialization_unknown"
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, needs_reconciliation=True)
            if operation in ("status", "verify_url") and (not isinstance(error, PublisherAPIError) or error.retryable):
                return pending_publish_result(self.platform_name, state, error_message=safe_provider_error(self.platform_name, error))
            if operation == "creator_info" and isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), retryable=True)
            return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, retryable=isinstance(error, PublisherAPIError) and error.retryable, needs_reconciliation=bool(state.get("post_ids")))

    def _query_video(self, video_id: str, fields: str) -> Dict[str, Any]:
        return self._http_request(f"video/query/?{urllib.parse.urlencode({'fields': fields})}", data={"filters": {"video_ids": [video_id]}})

    def schedule(self, media_uri: str, caption: str, disclosure: str, account_id: str, scheduled_at_iso: str, **kwargs) -> PublishResult:
        return self.publish(media_uri, caption, disclosure, account_id, **kwargs)

    def delete(self, external_post_id: str, account_id: str) -> bool:
        # Content Posting and Display APIs do not expose deletion of published posts.
        return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if not self.access_token:
            raise RuntimeError("TIKTOK_ACCESS_TOKEN is not configured")
        response = self._query_video(external_post_id, "id,view_count,like_count,comment_count,share_count")
        video = next((video for video in response.get("data", {}).get("videos", []) if str(video.get("id")) == str(external_post_id)), None)
        if video is None:
            raise RuntimeError("TikTok did not return the requested video metrics")
        return PlatformMetrics(
            platform=self.platform_name, post_id=external_post_id,
            views=int(video.get("view_count", 0)), likes=int(video.get("like_count", 0)),
            comments=int(video.get("comment_count", 0)), shares=int(video.get("share_count", 0)),
            raw_payload=response,
        )
