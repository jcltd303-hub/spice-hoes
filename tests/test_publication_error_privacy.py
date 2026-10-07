import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from spicecore.core import Store
from spicecore.distribution.base import PublishResult
from spicecore.distribution.instagram import InstagramGraphPublisher
from spicecore.distribution.scheduler import Scheduler
from spicecore.distribution.tiktok import TikTokPublisher
from spicecore.distribution.worker import OutboxWorker
from spicecore.distribution.youtube import YouTubeShortsPublisher
from tests.test_social_adapter_api import Boundary, CREATOR, Response, tiktok_response


SECRETS = ("PRIVATE_READ_SIGNATURE", "sk-secret-provider-key", "customer@example.com", "Jane Customer")
UNTRUSTED_ERROR = "Could not fetch https://cdn.example.com/asset.jpg?sp=r&sig=" + SECRETS[0] + " Authorization: Bearer " + SECRETS[1] + " " + " ".join(SECRETS[2:])


def api_error(platform, code=400):
    provider_code = "url_ownership_unverified" if platform == "tiktok" else 100
    body = {"error": {"code": provider_code, "message": UNTRUSTED_ERROR}}
    return urllib.error.HTTPError(
        "https://provider.example/api?sig=" + SECRETS[0], code, UNTRUSTED_ERROR,
        {"Authorization": "Bearer " + SECRETS[1]}, io.BytesIO(json.dumps(body).encode()),
    )


class TestProviderErrorPrivacy(unittest.TestCase):
    def assert_private(self, value):
        serialized = json.dumps(value, default=str)
        for secret in SECRETS:
            self.assertNotIn(secret, serialized)

    def test_instagram_http_error_exposes_code_without_body_or_signed_url(self):
        publisher = InstagramGraphPublisher(access_token="test-token")
        with patch("urllib.request.urlopen", side_effect=api_error("instagram")):
            result = publisher.publish(
                "https://cdn.example.com/portrait.jpg?sig=" + SECRETS[0],
                "A portrait", "Fictional AI character", "account-1",
            )
        self.assertFalse(result.success)
        self.assert_private(result.to_dict())
        self.assertIn("100", result.error_message)

    def test_tiktok_http_error_exposes_known_code_without_response_message(self):
        publisher = TikTokPublisher(access_token="test-token", privacy_level="PUBLIC_TO_EVERYONE")
        boundary = Boundary(tiktok_response(CREATOR), api_error("tiktok"))
        with patch("urllib.request.urlopen", side_effect=boundary):
            result = publisher.publish("https://cdn.example.com/clip.mp4", "A clip", "Fictional AI character", "creator")
        self.assertFalse(result.success)
        self.assert_private(result.to_dict())
        self.assertIn("url_ownership_unverified", result.error_message)

    def test_youtube_http_and_metrics_errors_do_not_include_raw_provider_text(self):
        publisher = YouTubeShortsPublisher(access_token="test-token")
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "clip.mp4"
            video.write_bytes(b"video bytes")
            with patch("urllib.request.urlopen", side_effect=api_error("youtube_shorts")):
                result = publisher.publish(str(video), "A clip", "Fictional AI character", "channel-1")
        self.assertFalse(result.success)
        self.assert_private(result.to_dict())
        with patch("urllib.request.urlopen", side_effect=api_error("youtube_shorts")):
            with self.assertRaises(RuntimeError) as error:
                publisher.fetch_metrics("abc123def45", "channel-1")
        self.assert_private(str(error.exception))

    def test_connection_exception_text_is_not_returned_by_adapters(self):
        publisher = InstagramGraphPublisher(access_token="test-token")
        with patch("urllib.request.urlopen", side_effect=TimeoutError(UNTRUSTED_ERROR)):
            result = publisher.publish("https://cdn.example.com/portrait.jpg", "A portrait", "Fictional AI character", "account-1")
        self.assert_private(result.to_dict())
        self.assertIn("TimeoutError", result.error_message)


class TestWorkerErrorPrivacy(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temporary.name) / "queue.sqlite")
        self.video = Path(self.temporary.name) / "clip.mp4"
        self.video.write_bytes(b"video bytes")
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(self.store)
        candidate_id = self.store.propose(
            {"id": "lila_hart", "version": "test", "name": "Lila"},
            "Ceramics", "video", "mock_social", "guide", asset_uri=str(self.video),
        )
        self.store.review(candidate_id, "approved", "policy:v1")
        self.post = self.scheduler.schedule_candidate(candidate_id, "mock_social", "channel-1", "2026-10-01T10:00:00Z")

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def assert_private(self, value):
        serialized = json.dumps(value, default=str)
        for secret in SECRETS:
            self.assertNotIn(secret, serialized)

    def test_arbitrary_publisher_failure_text_is_not_returned_or_audited(self):
        publisher = Mock()
        publisher.publish.return_value = PublishResult(
            success=False, platform="mock_social", error_message=UNTRUSTED_ERROR,
            response_metadata={"error": {"message": UNTRUSTED_ERROR}, "headers": {"Authorization": SECRETS[1]}},
        )
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        result = worker.process_due("2026-10-01T10:00:00Z")[0]
        self.assert_private(result.to_dict())
        self.assert_private(Scheduler(self.store).get_post(self.post.schedule_id).last_error)
        self.assert_private(self.store.events())

    def test_arbitrary_pending_error_is_not_persisted_or_returned(self):
        publisher = Mock()
        publisher.publish.return_value = PublishResult(
            success=False, pending=True, platform="mock_social", error_message=UNTRUSTED_ERROR,
            response_metadata={"pending": True, "provider_state": {"operation_id": "op-1"}, "response": {"error": UNTRUSTED_ERROR}},
        )
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        result = worker.process_due("2026-10-01T10:00:00Z")[0]
        self.assertTrue(result.pending)
        self.assert_private(result.to_dict())
        self.assert_private(Scheduler(self.store).get_post(self.post.schedule_id).last_error)
        self.assert_private(self.store.events())

    def test_raised_publisher_exception_does_not_leak_to_logging_or_audit(self):
        publisher = Mock()
        publisher.publish.side_effect = TimeoutError(UNTRUSTED_ERROR)
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        with self.assertLogs(level="WARNING") as logs:
            result = worker.process_due("2026-10-01T10:00:00Z")[0]
        self.assert_private(logs.output)
        self.assert_private(result.to_dict())
        self.assert_private(self.store.events())


if __name__ == "__main__":
    unittest.main()
