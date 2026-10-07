"""YouTube video upload with durable resumable sessions and publication checks."""

from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    PublisherValidationError, safe_provider_error,
    PlatformMetrics, Publisher, PublisherAPIError, PublishResult,
    failed_publish_result, pending_publish_result, resume_provider_state,
)


class YouTubeShortsPublisher(Publisher):
    """Upload real local video bytes, then confirm public processed media.

    https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
    A hashtag does not make a video a Short. YouTube classifies square/vertical
    videos up to three minutes; the canonical watch URL works for either format.
    """

    def __init__(self, access_token: Optional[str] = None, chunk_size: int = 8 * 1024 * 1024):
        self.access_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "") if access_token is None else access_token
        # The documented resumable protocol requires multiples of 256 KiB.
        if chunk_size <= 0 or chunk_size % (256 * 1024):
            raise PublisherValidationError("YouTube chunk_size must be a positive multiple of 256 KiB")
        self.chunk_size = chunk_size
        self.upload_url = "https://www.googleapis.com/upload/youtube/v3/videos"
        self.api_url = "https://www.googleapis.com/youtube/v3"

    @property
    def platform_name(self) -> str:
        return "youtube_shorts"

    def _request(self, url: str, *, method: str = "GET", data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, Any], int, Dict[str, str]]:
        request = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {self.access_token}", **(headers or {})}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 308:
                return {}, 308, {key.lower(): value for key, value in error.headers.items()}
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error", {})
            except (ValueError, UnicodeDecodeError):
                detail = {}
            raise PublisherAPIError(
                safe_provider_error(self.platform_name, code=error.code),
                retryable=error.code == 429 or error.code >= 500,
                ambiguous=error.code >= 500,
            ) from error
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            raise PublisherValidationError("YouTube returned a malformed response")
        if payload.get("error"):
            raise PublisherAPIError(safe_provider_error(self.platform_name, code=payload['error'].get('code')))
        return payload, status, response_headers

    @staticmethod
    def _local_video(media_uri: str) -> Path:
        parsed = urllib.parse.urlsplit(media_uri)
        if parsed.scheme and parsed.scheme != "file":
            raise PublisherValidationError("YouTube upload requires a local video file; download hosted video before scheduling")
        if parsed.scheme == "file" and parsed.netloc not in ("", "localhost"):
            raise PublisherValidationError("YouTube file URI must refer to a local file")
        path = Path(urllib.parse.unquote(parsed.path) if parsed.scheme == "file" else media_uri).expanduser().resolve()
        if not path.is_file():
            raise PublisherValidationError("YouTube media file does not exist")
        return path

    @staticmethod
    def _session_url(url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com" or parsed.username or parsed.password:
            raise PublisherValidationError("YouTube returned an invalid resumable upload URL")
        return url

    @staticmethod
    def _offset(headers: Dict[str, str], total: int) -> int:
        value = headers.get("range")
        if not value:
            return 0
        match = re.fullmatch(r"bytes=0-(\d+)", value)
        if not match:
            raise PublisherValidationError("YouTube returned an invalid upload byte range")
        offset = int(match.group(1)) + 1
        if offset > total:
            raise PublisherValidationError("YouTube upload byte range exceeds the source file")
        return offset

    def publish(
        self, media_uri: str, caption: str, disclosure: str, account_id: str,
        idempotency_key: Optional[str] = None, hashtags: Optional[List[str]] = None,
        resume_metadata: Optional[Dict[str, Any]] = None, **kwargs,
    ) -> PublishResult:
        if not self.access_token:
            return failed_publish_result(self.platform_name, "YOUTUBE_ACCESS_TOKEN is not configured")
        state: Dict[str, Any] = {}
        operation = "validate"
        try:
            state = resume_provider_state(resume_metadata, self.platform_name, account_id)
            if state and state.get("phase") == "initialization_unknown":
                return failed_publish_result(self.platform_name, "YouTube initialization outcome requires reconciliation before another upload", state, needs_reconciliation=True)
            if not state:
                path = self._local_video(media_uri)
                stat = path.stat()
                if not 0 < stat.st_size <= 256 * 1024 ** 3:
                    raise PublisherValidationError("YouTube requires a nonempty video file no larger than 256 GB")
                content_type = mimetypes.guess_type(path.name)[0]
                if not content_type or not content_type.startswith("video/"):
                    raise PublisherValidationError("YouTube media must be a video file with a recognized video MIME type")
                duration = kwargs.get("duration_seconds")
                if duration is not None and (not math.isfinite(float(duration)) or not 0 < float(duration) <= 180):
                    raise PublisherValidationError("YouTube Shorts must be no longer than 180 seconds")
                ratio = kwargs.get("aspect_ratio")
                if ratio:
                    width, height = (float(part) for part in str(ratio).split(":"))
                    if not (0 < width <= height and math.isfinite(height)):
                        raise PublisherValidationError("YouTube Shorts require a square or vertical aspect ratio")
                title = str(kwargs.get("title") or f"{caption[:90]} #Shorts").strip()
                description = "\n\n".join(text for text in (caption, disclosure) if text)
                if hashtags:
                    description += "\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
                if not title or len(title) > 100 or any(character in title for character in "<>"):
                    raise PublisherValidationError("YouTube title must contain 1-100 characters and no angle brackets")
                if len(description.encode("utf-8")) > 5000:
                    raise PublisherValidationError("YouTube description exceeds 5,000 bytes")
                if not account_id:
                    raise PublisherValidationError("YouTube account_id is required")
                metadata = {
                    "snippet": {"title": title, "description": description, "categoryId": "24"},
                    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
                }
                if hashtags:
                    metadata["snippet"]["tags"] = [tag.lstrip("#") for tag in hashtags]
                encoded_metadata = json.dumps(metadata).encode("utf-8")
                operation = "account"
                channels, _, _ = self._request(f"{self.api_url}/channels?part=id&mine=true")
                authorized_channels = channels.get("items", [])
                if len(authorized_channels) != 1 or str(authorized_channels[0].get("id", "")) != account_id:
                    raise PublisherValidationError("YouTube account_id must match the single authenticated channel ID")
                state = {
                    "platform": self.platform_name, "account_id": account_id,
                    "source_path": str(path), "file_size": stat.st_size,
                    "file_mtime_ns": stat.st_mtime_ns, "content_type": content_type,
                    "uploaded_bytes": 0, "chunk_size": self.chunk_size,
                }
                operation = "initialize"
                _, status, headers = self._request(
                    f"{self.upload_url}?uploadType=resumable&part=snippet,status",
                    method="POST", data=encoded_metadata,
                    headers={"Content-Type": "application/json; charset=UTF-8", "Content-Length": str(len(encoded_metadata)), "X-Upload-Content-Type": content_type, "X-Upload-Content-Length": str(stat.st_size)},
                )
                if status not in (200, 201) or not headers.get("location"):
                    raise PublisherValidationError("YouTube did not return a resumable upload session")
                state.update(upload_url=self._session_url(headers["location"]), phase="upload", must_probe=False)
                # Save the session before transferring any bytes.
                return pending_publish_result(self.platform_name, state)

            if not state.get("video_id"):
                if not state.get("upload_url"):
                    raise PublisherValidationError("YouTube provider state lacks an upload_url or video_id")
                session_url = self._session_url(state["upload_url"])
                path = self._local_video(media_uri)
                stat = path.stat()
                total = int(state["file_size"])
                if str(path) != state.get("source_path") or stat.st_size != total or stat.st_mtime_ns != int(state["file_mtime_ns"]):
                    raise PublisherValidationError("YouTube source video changed during the resumable upload")
                if state.get("must_probe", True):
                    operation = "probe"
                    response, status, headers = self._request(session_url, method="PUT", data=b"", headers={"Content-Length": "0", "Content-Range": f"bytes */{total}"})
                    # Never guess how many bytes an interrupted request delivered.
                    if status == 308:
                        state.update(uploaded_bytes=self._offset(headers, total), must_probe=False)
                        return pending_publish_result(self.platform_name, state, response)
                else:
                    offset = int(state.get("uploaded_bytes", 0))
                    if not 0 <= offset < total:
                        state["must_probe"] = True
                        return pending_publish_result(self.platform_name, state, error_message="Waiting for upload completion receipt")
                    chunk_size = int(state.get("chunk_size", self.chunk_size))
                    if chunk_size <= 0 or chunk_size % (256 * 1024):
                        raise PublisherValidationError("Invalid persisted YouTube chunk size")
                    with path.open("rb") as video:
                        video.seek(offset)
                        video_bytes = video.read(min(chunk_size, total - offset))
                    if not video_bytes:
                        raise PublisherValidationError("YouTube video source has no remaining media bytes")
                    operation = "upload"
                    response, status, headers = self._request(
                        session_url, method="PUT", data=video_bytes,
                        headers={"Content-Type": state["content_type"], "Content-Length": str(len(video_bytes)), "Content-Range": f"bytes {offset}-{offset + len(video_bytes) - 1}/{total}"},
                    )
                    if status == 308:
                        state.update(uploaded_bytes=self._offset(headers, total), must_probe=False)
                        return pending_publish_result(self.platform_name, state, response)
                if status not in (200, 201) or not response.get("id"):
                    state["must_probe"] = True
                    return pending_publish_result(self.platform_name, state, response, "YouTube has not returned a video ID; verify the retained upload session")
                state.update(video_id=str(response["id"]), uploaded_bytes=total, phase="processing", must_probe=False)
                return pending_publish_result(self.platform_name, state, response)

            operation = "verify"
            video_id = str(state["video_id"])
            if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
                raise PublisherValidationError("YouTube returned an invalid video ID")
            response, _, _ = self._request(f"{self.api_url}/videos?{urllib.parse.urlencode({'id': video_id, 'part': 'snippet,status,processingDetails'})}")
            video = next((item for item in response.get("items", []) if str(item.get("id")) == video_id), None)
            if video is None:
                return pending_publish_result(self.platform_name, state, response, "Waiting for YouTube to return the uploaded video")
            status = video.get("status", {})
            processing = video.get("processingDetails", {})
            upload_status = status.get("uploadStatus")
            processing_status = processing.get("processingStatus")
            state.update(upload_status=upload_status, processing_status=processing_status)
            if upload_status in ("failed", "rejected", "deleted") or processing_status == "failed":
                reason = status.get("failureReason") or status.get("rejectionReason") or processing.get("processingFailureReason") or upload_status
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, code=reason), state)
            if upload_status != "processed" or processing_status not in (None, "succeeded", "terminated"):
                return pending_publish_result(self.platform_name, state, response)
            if status.get("privacyStatus") != "public":
                return failed_publish_result(self.platform_name, "YouTube processed the upload but did not make it public; verify channel privacy and API project audit status", state, needs_reconciliation=True)
            state["phase"] = "published"
            # The ID and public/processed status are from videos.list, not metadata.
            return PublishResult(
                success=True, platform=self.platform_name, external_post_id=video_id,
                canonical_url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=video.get("snippet", {}).get("publishedAt"),
                response_metadata={"provider_state": state, "response": response},
            )
        except Exception as error:
            rejected = isinstance(error, PublisherAPIError) and not error.ambiguous
            if operation == "initialize" and not rejected:
                state["phase"] = "initialization_unknown"
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, needs_reconciliation=True)
            if operation in ("upload", "probe", "verify") and (not isinstance(error, PublisherAPIError) or error.retryable):
                if operation in ("upload", "probe"):
                    state["must_probe"] = True
                return pending_publish_result(self.platform_name, state, error_message=safe_provider_error(self.platform_name, error))
            if operation == "account" and isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
                return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), retryable=True)
            return failed_publish_result(self.platform_name, safe_provider_error(self.platform_name, error), state, retryable=isinstance(error, PublisherAPIError) and error.retryable, needs_reconciliation=operation in ("upload", "probe", "verify"))

    def schedule(self, media_uri: str, caption: str, disclosure: str, account_id: str, scheduled_at_iso: str, **kwargs) -> PublishResult:
        return self.publish(media_uri, caption, disclosure, account_id, **kwargs)

    def delete(self, external_post_id: str, account_id: str) -> bool:
        if not self.access_token:
            return False
        try:
            _, status, _ = self._request(f"{self.api_url}/videos?{urllib.parse.urlencode({'id': external_post_id})}", method="DELETE")
            return status in (200, 204)
        except Exception:
            return False

    def fetch_metrics(self, external_post_id: str, account_id: str) -> PlatformMetrics:
        if not self.access_token:
            raise RuntimeError("YOUTUBE_ACCESS_TOKEN is not configured")
        response, _, _ = self._request(f"{self.api_url}/videos?{urllib.parse.urlencode({'id': external_post_id, 'part': 'statistics'})}")
        video = next((item for item in response.get("items", []) if str(item.get("id")) == str(external_post_id)), None)
        if video is None:
            raise RuntimeError("YouTube did not return the requested video statistics")
        statistics = video.get("statistics", {})
        return PlatformMetrics(
            platform=self.platform_name, post_id=external_post_id,
            views=int(statistics.get("viewCount", 0)), likes=int(statistics.get("likeCount", 0)),
            comments=int(statistics.get("commentCount", 0)), raw_payload=response,
        )
