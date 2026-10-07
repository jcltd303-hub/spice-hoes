"""Instagram Graph API publishing for JPEG photos and Reels."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from .base import (
    PublisherValidationError, safe_provider_error,
    PlatformMetrics, Publisher, PublisherAPIError, PublishResult,
    failed_publish_result, pending_publish_result, require_public_media_url,
    resume_provider_state,
)


class InstagramGraphPublisher(Publisher):
    """Facebook Login API; needs a linked professional Instagram account.

    Container creation and status polling follow Meta's official collection:
    https://www.postman.com/meta/instagram/collection/6yqw8pt/instagram-api
    """

    def __init__(self, access_token: Optional[str] = None, api_version: str = "v21.0"):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "") if access_token is None else access_token
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _http_request(self, endpoint: str, data: Optional[Dict[str, Any]] = None, method: str = "POST") -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        encoded_data = None
        if data is not None:
            values = {key: str(value).lower() if isinstance(value, bool) else value for key, value in data.items()}
            encoded = urllib.parse.urlencode(values)
            if method == "GET":
                url += ("&" if "?" in url else "?") + encoded
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                encoded_data = encoded.encode("utf-8")
        request = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
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
                retryable=error.code == 429 or error.code >= 500 or bool(detail.get("is_transient")),
                ambiguous=error.code >= 500,
            ) from error
        if not isinstance(payload, dict):
            raise PublisherValidationError("Instagram returned a malformed response")
        if payload.get("error"):
            detail = payload["error"]
            raise PublisherAPIError(safe_provider_error(self.platform_name, code=detail.get('code')), retryable=bool(detail.get("is_transient")))
        return payload

    def publish(
        self, media_uri: str, caption: str, disclosure: str, account_id: str,
        idempotency_key: Optional[str] = None, hashtags: Optional[List[str]] = None,
        resume_metadata: Optional[Dict[str, Any]] = None, **kwargs,
    ) -> PublishResult:
        if not self.access_token:
            return failed_publish_result(self.platform_name, "INSTAGRAM_ACCESS_TOKEN is not configured")
        state: Dict[str, Any] = {}
        operation = "validate"
        try:
            state = resume_provider_state(resume_metadata, self.platform_name, account_id)
            if state:
                if state.get("phase") in ("publication_unknown", "initialization_unknown"):
                    return failed_publish_result(self.platform_name, "Instagram submission outcome requires reconciliation before any retry", state, needs_reconciliation=True)
                if not state.get("container_id") and not state.get("media_id"):
                    raise PublisherValidationError("Instagram provider state lacks a container_id or media_id")
            else:
                require_public_media_url(media_uri)
                suffix = PurePosixPath(urllib.parse.urlsplit(media_uri).path).suffix.lower()
                media_kind = str(kwargs.get("media_type") or kwargs.get("mime_type") or "").upper()
                if suffix in (".png", ".webp", ".gif", ".heic"):
                    raise PublisherValidationError("Instagram still-image publishing requires JPEG; convert the asset before publishing")
                if media_kind in ("IMAGE", "PHOTO", "IMAGE/JPEG", "JPEG") or suffix in (".jpg", ".jpeg"):
                    source = {"image_url": media_uri}
                    media_kind = "image"
                elif media_kind in ("REELS", "VIDEO", "VIDEO/MP4", "VIDEO/QUICKTIME") or suffix in (".mp4", ".mov"):
                    source = {"media_type": "REELS", "video_url": media_uri, "share_to_feed": True}
                    media_kind = "video"
                else:
                    raise PublisherValidationError("Instagram requires a JPEG image URL or MP4/MOV Reel URL; specify media_type for URLs without an extension")
                full_caption = "\n\n".join(text for text in (caption, disclosure) if text)
                if hashtags:
                    full_caption += "\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
                if len(full_caption) > 2200 or full_caption.count("#") > 30:
                    raise PublisherValidationError("Instagram caption exceeds 2,200 characters or 30 hashtags")
                if not account_id:
                    raise PublisherValidationError("Instagram account_id is required")
                state = {"platform": self.platform_name, "account_id": account_id, "media_kind": media_kind}
                operation = "create"
                response = self._http_request(f"{account_id}/media", data={**source, "caption": full_caption})
                container_id = response.get("id")
                if not container_id:
                    raise PublisherValidationError("Instagram accepted container creation without returning an id")
                state.update(container_id=str(container_id), phase="processing")
                return pending_publish_result(self.platform_name, state, response)

            if not state.get("media_id"):
                operation = "status"
                response = self._http_request(str(state["container_id"]), {"fields": "status_code,status"}, method="GET")
                status = response.get("status_code")
                state["status_code"] = status
                if status in ("ERROR", "EXPIRED"):
                    return failed_publish_result(self.platform_name, f"Instagram container {status}", state)
                if status == "PUBLISHED":
                    return failed_publish_result(self.platform_name, "Instagram container was already published but its media ID is unknown", state, needs_reconciliation=True)
                if status != "FINISHED":
                    return pending_publish_result(self.platform_name, state, response)
                operation = "publish"
                response = self._http_request(f"{account_id}/media_publish", data={"creation_id": state["container_id"]})
                if not response.get("id"):
                    raise PublisherValidationError("Instagram publishing response did not include a media id")
                state.update(media_id=str(response["id"]), phase="published")

            operation = "permalink"
            media_id = state["media_id"]
            response = self._http_request(str(media_id), {"fields": "id,permalink,timestamp"}, method="GET")
            permalink = response.get("permalink")
            if str(response.get("id", "")) != str(media_id) or not permalink:
                return pending_publish_result(self.platform_name, state, response, "Instagram media is published; waiting for its verified permalink")
            parsed = urllib.parse.urlsplit(permalink)
            if parsed.scheme != "https" or parsed.hostname not in ("www.instagram.com", "instagram.com"):
                return failed_publish_result(self.platform_name, "Instagram returned an invalid permalink", state, needs_reconciliation=True)
            return PublishResult(
                success=True, platform=self.platform_name, external_post_id=str(media_id),
                canonical_url=permalink, published_at=response.get("timestamp"),
                response_metadata={"provider_state": state, "response": response},
            )
        except Exception as error:
            rejected = isinstance(error, PublisherAPIError) and not error.ambiguous
            if operation in ("create", "publish") and not rejected:
                state["phase"] = "initialization_unknown" if operation == "create" else "publication_unknown"
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, needs_reconciliation=True)
            if operation in ("status", "permalink") and (not isinstance(error, PublisherAPIError) or error.retryable):
                return pending_publish_result(self.platform_name, state, error_message=safe_provider_error(self.platform_name, error))
            return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, retryable=isinstance(error, PublisherAPIError) and error.retryable, needs_reconciliation=bool(state.get("media_id")))

    def schedule(self, media_uri: str, caption: str, disclosure: str, account_id: str, scheduled_at_iso: str, **kwargs) -> PublishResult:
        # The durable outbox invokes publish at the due time; this isn't native scheduling.
        return self.publish(media_uri, caption, disclosure, account_id, **kwargs)

    def delete(self, external_post_id: str, account_id: str) -> bool:
        # Instagram's official publishing API does not expose media deletion.
        return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if not self.access_token:
            raise RuntimeError("INSTAGRAM_ACCESS_TOKEN is not configured")
        response = self._http_request(f"{external_post_id}/insights", {"metric": "views,reach,saved,likes,comments,shares"}, method="GET")
        counts = {}
        for item in response.get("data", []):
            values = item.get("values") or [{}]
            value = item.get("total_value", {}).get("value", values[0].get("value", 0))
            counts[item.get("name")] = int(value or 0)
        return PlatformMetrics(
            platform=self.platform_name, post_id=external_post_id, views=counts.get("views", 0),
            likes=counts.get("likes", 0), comments=counts.get("comments", 0),
            shares=counts.get("shares", 0), saves=counts.get("saved", 0), raw_payload=response,
        )
