"""Official API boundaries: acceptance is not proof that media was published."""

import json
import io
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from spicecore.distribution.instagram import InstagramGraphPublisher
from spicecore.distribution.tiktok import TikTokPublisher
from spicecore.distribution.youtube import YouTubeShortsPublisher


class Response:
    def __init__(self, payload=None, status=200, headers=None):
        self.body = json.dumps(payload or {}).encode()
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class Boundary:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def tiktok_response(data=None, code="ok", message=""):
    return Response({"data": data or {}, "error": {"code": code, "message": message}})


CREATOR = {
    "creator_username": "creator",
    "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
    "comment_disabled": True,
    "duet_disabled": True,
    "stitch_disabled": True,
    "max_video_post_duration_sec": 60,
}


class InstagramAPITest(unittest.TestCase):
    def setUp(self):
        self.publisher = InstagramGraphPublisher(access_token="test-token")
        self.arguments = dict(
            media_uri="https://cdn.example.com/portrait.jpg?sig=asset",
            caption="A portrait",
            disclosure="Fictional AI-generated character",
            account_id="17841400000000000",
        )

    def test_jpeg_container_is_pending_then_poll_publishes_with_real_permalink(self):
        boundary = Boundary(
            Response({"id": "container-1"}),
            Response({"id": "container-1", "status_code": "IN_PROGRESS"}),
            Response({"id": "container-1", "status_code": "FINISHED"}),
            Response({"id": "media-1"}),
            Response({"id": "media-1", "permalink": "https://www.instagram.com/p/ActualShortcode/", "timestamp": "2026-10-06T12:00:00Z"}),
        )
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
            self.assertFalse(initial.success)
            self.assertTrue(initial.pending)
            self.assertIsNone(initial.external_post_id)
            created = urllib.parse.parse_qs(boundary.requests[0].data.decode())
            self.assertEqual(created["image_url"], [self.arguments["media_uri"]])
            self.assertNotIn("video_url", created)
            self.assertEqual(initial.response_metadata["provider_state"]["container_id"], "container-1")
            processing = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
            self.assertTrue(processing.pending)
            self.assertEqual(boundary.requests[-1].get_method(), "GET")
            self.assertIsNone(boundary.requests[-1].data)
            result = self.publisher.publish(**self.arguments, resume_metadata=processing.response_metadata["provider_state"])
        self.assertTrue(result.success)
        self.assertFalse(result.pending)
        self.assertEqual(result.external_post_id, "media-1")
        self.assertEqual(result.canonical_url, "https://www.instagram.com/p/ActualShortcode/")
        self.assertEqual(result.published_at, "2026-10-06T12:00:00Z")
        self.assertEqual(sum(urllib.parse.urlsplit(r.full_url).path.endswith("/media") for r in boundary.requests), 1)

    def test_video_uses_reels_source(self):
        boundary = Boundary(Response({"id": "container-video"}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**dict(self.arguments, media_uri="https://cdn.example.com/clip.mp4"))
        payload = urllib.parse.parse_qs(boundary.requests[0].data.decode())
        self.assertEqual(payload["video_url"], ["https://cdn.example.com/clip.mp4"])
        self.assertEqual(payload["media_type"], ["REELS"])
        self.assertTrue(result.pending)

    def test_missing_permalink_resumes_from_media_id_without_republishing(self):
        state = {"platform": "instagram", "account_id": self.arguments["account_id"], "container_id": "container-1"}
        boundary = Boundary(
            Response({"status_code": "FINISHED"}), Response({"id": "media-1"}), Response({"id": "media-1"}),
            Response({"id": "media-1", "permalink": "https://www.instagram.com/p/Real/"}),
        )
        with patch("urllib.request.urlopen", side_effect=boundary):
            waiting = self.publisher.publish(**self.arguments, resume_metadata=state)
            self.assertTrue(waiting.pending)
            self.assertFalse(waiting.success)
            self.assertIsNone(waiting.canonical_url)
            self.assertEqual(waiting.response_metadata["provider_state"]["media_id"], "media-1")
            done = self.publisher.publish(**self.arguments, resume_metadata=waiting.response_metadata["provider_state"])
        self.assertTrue(done.success)
        self.assertEqual(sum(r.get_method() == "POST" for r in boundary.requests), 1)

    def test_uncertain_publish_does_not_allow_automatic_resubmission(self):
        state = {"platform": "instagram", "account_id": self.arguments["account_id"], "container_id": "container-1"}
        boundary = Boundary(Response({"status_code": "FINISHED"}), TimeoutError("response lost"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments, resume_metadata=state)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertTrue(result.response_metadata["needs_reconciliation"])
        self.assertEqual(result.response_metadata["provider_state"]["container_id"], "container-1")

    def test_lost_container_response_blocks_another_initialization(self):
        boundary = Boundary(TimeoutError("response lost"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            uncertain = self.publisher.publish(**self.arguments)
        self.assertTrue(uncertain.response_metadata["needs_reconciliation"])
        with patch("urllib.request.urlopen") as http:
            resumed = self.publisher.publish(**self.arguments, resume_metadata=uncertain.response_metadata["provider_state"])
        self.assertFalse(resumed.success)
        self.assertTrue(resumed.response_metadata["needs_reconciliation"])
        http.assert_not_called()

    def test_resume_cannot_switch_accounts(self):
        with patch("urllib.request.urlopen") as http:
            result = self.publisher.publish(**self.arguments, resume_metadata={"platform": "instagram", "account_id": "a-different-account", "container_id": "container-1"})
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        http.assert_not_called()

    def test_local_or_non_jpeg_images_fail_without_an_http_request(self):
        for media_uri in ("/tmp/portrait.jpg", "https://cdn.example.com/portrait.png"):
            with self.subTest(media_uri=media_uri), patch("urllib.request.urlopen") as http:
                result = self.publisher.publish(**dict(self.arguments, media_uri=media_uri))
            self.assertFalse(result.success)
            self.assertFalse(result.retryable)
            http.assert_not_called()

    def test_failed_container_is_terminal(self):
        boundary = Boundary(Response({"status_code": "ERROR", "status": "Video format unsupported"}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments, resume_metadata={"container_id": "container-1"})
        self.assertFalse(result.success)
        self.assertFalse(result.pending)
        self.assertFalse(result.retryable)
        self.assertIn("ERROR", result.error_message)
        self.assertNotIn("unsupported", result.error_message)

    def test_metrics_use_get_and_report_only_received_counts(self):
        boundary = Boundary(Response({"data": [
            {"name": "views", "values": [{"value": 7}]},
            {"name": "likes", "total_value": {"value": 2}},
        ]}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.fetch_metrics("media-1", self.arguments["account_id"])
        self.assertEqual(boundary.requests[0].get_method(), "GET")
        self.assertIsNone(boundary.requests[0].data)
        self.assertEqual(result.views, 7)
        self.assertEqual(result.likes, 2)
        self.assertEqual(result.impressions, 0)


class TikTokAPITest(unittest.TestCase):
    def setUp(self):
        self.publisher = TikTokPublisher(access_token="test-token", privacy_level="PUBLIC_TO_EVERYONE")
        self.arguments = dict(media_uri="https://cdn.example.com/clip.mp4", caption="A clip", disclosure="Fictional AI character", account_id="creator")

    def test_init_is_pending_and_uses_current_creator_settings(self):
        boundary = Boundary(tiktok_response(CREATOR), tiktok_response({"publish_id": "provider-job-1"}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertTrue(result.pending)
        self.assertIsNone(result.external_post_id)
        self.assertIsNone(result.canonical_url)
        self.assertIsNone(result.published_at)
        self.assertEqual(result.response_metadata["provider_state"]["publish_id"], "provider-job-1")
        self.assertIn("creator_info/query", boundary.requests[0].full_url)
        payload = json.loads(boundary.requests[1].data)
        self.assertEqual(payload["source_info"]["video_url"], self.arguments["media_uri"])
        self.assertTrue(payload["post_info"]["disable_duet"])
        self.assertTrue(payload["post_info"]["disable_comment"])
        self.assertTrue(payload["post_info"]["is_aigc"])

    def test_complete_status_and_api_share_url_confirm_actual_post(self):
        boundary = Boundary(
            tiktok_response({"status": "PROCESSING_DOWNLOAD"}),
            tiktok_response({"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [123456789]}),
            tiktok_response({"videos": [{"id": "123456789", "share_url": "https://www.tiktok.com/@real/video/123456789", "create_time": 1791288000}]}),
        )
        with patch("urllib.request.urlopen", side_effect=boundary):
            waiting = self.publisher.publish(**self.arguments, resume_metadata={"publish_id": "provider-job-1"})
            self.assertTrue(waiting.pending)
            result = self.publisher.publish(**self.arguments, resume_metadata=waiting.response_metadata["provider_state"])
        self.assertTrue(result.success)
        self.assertEqual(result.external_post_id, "123456789")
        self.assertEqual(result.canonical_url, "https://www.tiktok.com/@real/video/123456789")
        self.assertTrue(all("video/init" not in r.full_url for r in boundary.requests))
        self.assertEqual(boundary.requests[0].get_method(), "POST")
        self.assertEqual(json.loads(boundary.requests[0].data), {"publish_id": "provider-job-1"})
        self.assertIn("share_url", urllib.parse.parse_qs(urllib.parse.urlsplit(boundary.requests[-1].full_url).query)["fields"][0])

    def test_complete_without_post_id_or_share_url_never_invents_success(self):
        for data, extra in (({"status": "PUBLISH_COMPLETE"}, []), ({"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [123]}, [tiktok_response({"videos": [{"id": "123"}]})])):
            boundary = Boundary(tiktok_response(data), *extra)
            with self.subTest(data=data), patch("urllib.request.urlopen", side_effect=boundary):
                result = self.publisher.publish(**self.arguments, resume_metadata={"publish_id": "provider-job-1"})
            self.assertFalse(result.success)
            self.assertTrue(result.pending)
            self.assertIsNone(result.canonical_url)

    def test_http_200_api_error_is_failure(self):
        boundary = Boundary(tiktok_response(CREATOR), tiktok_response(code="url_ownership_unverified", message="Verify URL ownership"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertFalse(result.pending)
        self.assertFalse(result.retryable)
        self.assertIn("url_ownership_unverified", result.error_message)
        self.assertIsNone(result.external_post_id)

    def test_missing_publish_id_requires_reconciliation(self):
        boundary = Boundary(tiktok_response(CREATOR), tiktok_response())
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertTrue(result.response_metadata["needs_reconciliation"])

    def test_wrong_authenticated_creator_cannot_initialize_a_post(self):
        boundary = Boundary(tiktok_response(dict(CREATOR, creator_username="different_creator")))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(len(boundary.requests), 1)
        self.assertIn("authorized creator", result.error_message)

    def test_lost_init_response_cannot_be_retried_as_a_new_post(self):
        boundary = Boundary(tiktok_response(CREATOR), TimeoutError("response lost"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertTrue(result.response_metadata["needs_reconciliation"])
        with patch("urllib.request.urlopen") as http:
            resumed = self.publisher.publish(**self.arguments, resume_metadata=result.response_metadata["provider_state"])
        self.assertFalse(resumed.success)
        self.assertTrue(resumed.response_metadata["needs_reconciliation"])
        http.assert_not_called()

    def test_requires_an_explicit_allowed_privacy_level(self):
        boundary = Boundary(tiktok_response(dict(CREATOR, privacy_level_options=["SELF_ONLY"])))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(len(boundary.requests), 1)
        self.assertIn("privacy", result.error_message.lower())

    def test_failed_status_does_not_reinitialize(self):
        boundary = Boundary(tiktok_response({"status": "FAILED", "fail_reason": "duration_check_failed"}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments, resume_metadata={"publish_id": "provider-job-1"})
        self.assertFalse(result.pending)
        self.assertFalse(result.retryable)
        self.assertIn("duration_check_failed", result.error_message)
        self.assertEqual(len(boundary.requests), 1)

    def test_metrics_request_fields_and_do_not_invent_reach_or_saves(self):
        boundary = Boundary(tiktok_response({"videos": [{"id": "123", "view_count": 10, "like_count": 3, "comment_count": 2, "share_count": 1}]}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            metrics = self.publisher.fetch_metrics("123", "creator")
        self.assertEqual(boundary.requests[0].get_method(), "POST")
        self.assertIn("view_count", urllib.parse.parse_qs(urllib.parse.urlsplit(boundary.requests[0].full_url).query)["fields"][0])
        self.assertEqual(metrics.views, 10)
        self.assertEqual(metrics.impressions, 0)
        self.assertEqual(metrics.saves, 0)

    def test_unsupported_delete_does_not_call_invented_api(self):
        with patch("urllib.request.urlopen") as http:
            self.assertFalse(self.publisher.delete("123", "creator"))
        http.assert_not_called()


class YouTubeAPITest(unittest.TestCase):
    def setUp(self):
        self.publisher = YouTubeShortsPublisher(access_token="test-token")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.video = Path(self.temporary.name) / "clip.mp4"
        self.video_bytes = b"\x00\x00\x00\x18ftypmp42-real-video-bytes"
        self.video.write_bytes(self.video_bytes)
        self.arguments = dict(media_uri=str(self.video), caption="A clip", disclosure="Fictional AI-generated character", account_id="channel-1")
        self.session = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=test-session"

    def test_resumable_sends_actual_bytes_and_waits_for_public_processing(self):
        boundary = Boundary(
            Response({"items": [{"id": "channel-1"}]}),
            Response(headers={"Location": self.session}),
            Response({"id": "abc123def45", "status": {"uploadStatus": "uploaded"}}, status=201),
            Response({"items": [{"id": "abc123def45", "status": {"uploadStatus": "uploaded", "privacyStatus": "public"}, "processingDetails": {"processingStatus": "processing"}}]}),
            Response({"items": [{"id": "abc123def45", "snippet": {"publishedAt": "2026-10-06T12:00:00Z"}, "status": {"uploadStatus": "processed", "privacyStatus": "public"}, "processingDetails": {"processingStatus": "succeeded"}}]}),
        )
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
            self.assertTrue(initial.pending)
            self.assertFalse(initial.success)
            self.assertEqual(initial.response_metadata["provider_state"]["upload_url"], self.session)
            self.assertEqual(boundary.requests[0].get_method(), "GET")
            self.assertIn("mine=true", boundary.requests[0].full_url)
            self.assertEqual(boundary.requests[1].get_header("X-upload-content-length"), str(len(self.video_bytes)))
            self.assertTrue(json.loads(boundary.requests[1].data)["status"]["containsSyntheticMedia"])
            uploaded = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
            self.assertTrue(uploaded.pending)
            self.assertFalse(uploaded.success)
            self.assertEqual(boundary.requests[2].get_method(), "PUT")
            self.assertEqual(boundary.requests[2].data, self.video_bytes)
            self.assertEqual(boundary.requests[2].get_header("Content-type"), "video/mp4")
            processing = self.publisher.publish(**self.arguments, resume_metadata=uploaded.response_metadata["provider_state"])
            self.assertTrue(processing.pending)
            completed = self.publisher.publish(**self.arguments, resume_metadata=processing.response_metadata["provider_state"])
        self.assertTrue(completed.success)
        self.assertEqual(completed.external_post_id, "abc123def45")
        self.assertEqual(completed.canonical_url, "https://www.youtube.com/watch?v=abc123def45")
        self.assertEqual(sum(r.get_method() == "POST" for r in boundary.requests), 1)
        self.assertEqual(boundary.requests[-1].get_method(), "GET")

    def test_interrupted_upload_probes_provider_before_resending_bytes(self):
        boundary = Boundary(Response({"items": [{"id": "channel-1"}]}), Response(headers={"Location": self.session}), TimeoutError("connection interrupted"), Response(status=308, headers={"Range": "bytes=0-9"}), Response({"id": "abc123def45"}, status=201))
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
            interrupted = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
            self.assertTrue(interrupted.pending)
            self.assertEqual(interrupted.response_metadata["provider_state"]["upload_url"], self.session)
            resumed = self.publisher.publish(**self.arguments, resume_metadata=interrupted.response_metadata["provider_state"])
            self.assertTrue(resumed.pending)
            if len(boundary.requests) == 4:
                resumed = self.publisher.publish(**self.arguments, resume_metadata=resumed.response_metadata["provider_state"])
        self.assertEqual(boundary.requests[3].data, b"")
        self.assertEqual(boundary.requests[3].get_header("Content-range"), f"bytes */{len(self.video_bytes)}")
        self.assertEqual(boundary.requests[4].data, self.video_bytes[10:])
        self.assertEqual(boundary.requests[4].get_header("Content-range"), f"bytes 10-{len(self.video_bytes)-1}/{len(self.video_bytes)}")
        self.assertEqual(sum(r.get_method() == "POST" for r in boundary.requests), 1)

    def test_private_or_rejected_video_never_counts_as_publication(self):
        for status in ({"uploadStatus": "processed", "privacyStatus": "private"}, {"uploadStatus": "rejected", "privacyStatus": "public", "rejectionReason": "copyright"}):
            boundary = Boundary(Response({"items": [{"id": "abc123def45", "status": status, "processingDetails": {"processingStatus": "succeeded"}}]}))
            with self.subTest(status=status), patch("urllib.request.urlopen", side_effect=boundary):
                result = self.publisher.publish(**self.arguments, resume_metadata={"video_id": "abc123def45"})
            self.assertFalse(result.success)
            self.assertFalse(result.retryable)
            self.assertIsNone(result.canonical_url)
            self.assertEqual(len(boundary.requests), 1)

    def test_metadata_only_upload_response_never_counts_as_success(self):
        boundary = Boundary(Response({"items": [{"id": "channel-1"}]}), Response(headers={"Location": self.session}), Response({"snippet": {"title": "A clip"}}, status=201))
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
            result = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
        self.assertFalse(result.success)
        self.assertIsNone(result.canonical_url)
        self.assertTrue(result.pending or result.response_metadata.get("needs_reconciliation"))

    def test_missing_local_video_fails_without_creating_upload(self):
        with patch("urllib.request.urlopen") as http:
            result = self.publisher.publish(**dict(self.arguments, media_uri=str(self.video.parent / "missing.mp4")))
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        http.assert_not_called()

    def test_wrong_authenticated_channel_cannot_start_upload(self):
        boundary = Boundary(Response({"items": [{"id": "different-channel"}]}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments)
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(len(boundary.requests), 1)
        self.assertEqual(boundary.requests[0].get_method(), "GET")

    def test_changed_source_is_not_sent_to_an_existing_upload(self):
        boundary = Boundary(Response({"items": [{"id": "channel-1"}]}), Response(headers={"Location": self.session}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
        self.video.write_bytes(b"changed video content")
        with patch("urllib.request.urlopen") as http:
            result = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        http.assert_not_called()

    def test_urllib_308_is_a_resumable_response(self):
        boundary = Boundary(Response({"items": [{"id": "channel-1"}]}), Response(headers={"Location": self.session}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
        boundary = Boundary(urllib.error.HTTPError(self.session, 308, "Resume Incomplete", {"Range": "bytes=0-9"}, io.BytesIO()))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
        self.assertTrue(result.pending)
        self.assertEqual(result.response_metadata["provider_state"]["uploaded_bytes"], 10)

    def test_lost_session_response_is_not_freshly_submitted_on_resume(self):
        boundary = Boundary(Response({"items": [{"id": "channel-1"}]}), TimeoutError("response lost"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            initial = self.publisher.publish(**self.arguments)
        self.assertTrue(initial.response_metadata["needs_reconciliation"])
        with patch("urllib.request.urlopen") as http:
            resumed = self.publisher.publish(**self.arguments, resume_metadata=initial.response_metadata["provider_state"])
        self.assertFalse(resumed.success)
        self.assertTrue(resumed.response_metadata["needs_reconciliation"])
        http.assert_not_called()

    def test_metrics_do_not_fabricate_impressions_from_views(self):
        boundary = Boundary(Response({"items": [{"id": "abc123def45", "statistics": {"viewCount": "8", "likeCount": "2", "commentCount": "1"}}]}))
        with patch("urllib.request.urlopen", side_effect=boundary):
            metrics = self.publisher.fetch_metrics("abc123def45", "channel-1")
        self.assertEqual(boundary.requests[0].get_method(), "GET")
        self.assertEqual(metrics.views, 8)
        self.assertEqual(metrics.impressions, 0)


if __name__ == "__main__":
    unittest.main()
