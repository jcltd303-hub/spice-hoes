import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spicecore.core import Store
from spicecore.distribution.scheduler import Scheduler, ScheduleStatus
from spicecore.distribution.worker import OutboxWorker
from spicecore.distribution.youtube import YouTubeShortsPublisher


class TestYouTubeClaimRecovery(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temporary.name) / "queue.sqlite")
        self.video = Path(self.temporary.name) / "clip.mp4"
        self.video.write_bytes(b"0123456789")
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(self.store)
        candidate_id = self.store.propose(
            {"id": "lila_hart", "version": "test", "name": "Lila"},
            "Ceramics", "video", "youtube_shorts", "guide", asset_uri=str(self.video),
        )
        self.store.review(candidate_id, "approved", "policy:v1")
        self.post = self.scheduler.schedule_candidate(
            candidate_id, "youtube_shorts", "channel-1", "2026-10-01T10:00:00Z",
            caption="Ceramics", disclosure="Fictional AI character",
        )
        stat = self.video.stat()
        self.session = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=test-session"
        self.post.provider_state = {
            "platform": "youtube_shorts", "account_id": "channel-1",
            "source_path": str(self.video.resolve()), "file_size": 10,
            "file_mtime_ns": stat.st_mtime_ns, "content_type": "video/mp4",
            "uploaded_bytes": 0, "chunk_size": 8 * 1024 * 1024,
            "upload_url": self.session, "phase": "upload", "must_probe": False,
        }
        self.post.status = ScheduleStatus.PENDING
        self.scheduler.save_post(self.post)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def restart(self):
        self.store.close()
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(self.store)

    def test_hard_crash_forces_probe_and_resumes_from_provider_acknowledgment(self):
        self.scheduler.claim_post(self.post.schedule_id, "2026-10-01T10:00:00Z")
        # A terminated process cannot persist the provider's accepted byte count.
        self.restart()
        publisher = YouTubeShortsPublisher(access_token="test-token")
        worker = OutboxWorker(self.scheduler, {"youtube_shorts": publisher}, self.store)
        with patch.object(publisher, "_request", return_value=({}, 308, {"range": "bytes=0-3"})) as request:
            result = worker.process_due("2026-10-01T10:05:01Z")[0]
        self.assertTrue(result.pending)
        request.assert_called_once_with(
            self.session, method="PUT", data=b"",
            headers={"Content-Length": "0", "Content-Range": "bytes */10"},
        )
        persisted = self.scheduler.get_post(self.post.schedule_id)
        self.assertEqual(persisted.status, ScheduleStatus.PENDING)
        self.assertEqual(persisted.provider_state["uploaded_bytes"], 4)
        self.assertFalse(persisted.provider_state["must_probe"])

        # A normally completed pending tick can use that newly confirmed offset.
        self.restart()
        worker = OutboxWorker(self.scheduler, {"youtube_shorts": publisher}, self.store)
        with patch.object(publisher, "_request", return_value=({"id": "abc123def45"}, 201, {})) as request:
            result = worker.process_due("2026-10-01T10:06:00Z")[0]
        self.assertTrue(result.pending)
        request.assert_called_once_with(
            self.session, method="PUT", data=b"456789",
            headers={"Content-Type": "video/mp4", "Content-Length": "6", "Content-Range": "bytes 4-9/10"},
        )
        self.assertEqual(self.scheduler.get_post(self.post.schedule_id).provider_state["video_id"], "abc123def45")

    def test_recovery_probe_can_discover_upload_already_completed(self):
        self.scheduler.claim_post(self.post.schedule_id, "2026-10-01T10:00:00Z")
        self.restart()
        publisher = YouTubeShortsPublisher(access_token="test-token")
        worker = OutboxWorker(self.scheduler, {"youtube_shorts": publisher}, self.store)
        with patch.object(publisher, "_request", return_value=({"id": "abc123def45"}, 201, {})) as request:
            result = worker.process_due("2026-10-01T10:05:01Z")[0]
        self.assertTrue(result.pending)
        self.assertFalse(result.success)
        self.assertEqual(request.call_args.kwargs["data"], b"")
        self.assertEqual(request.call_args.kwargs["headers"]["Content-Range"], "bytes */10")
        persisted = self.scheduler.get_post(self.post.schedule_id)
        self.assertEqual(persisted.provider_state["video_id"], "abc123def45")
        self.assertEqual(persisted.provider_state["phase"], "processing")

    def test_recovery_persists_probe_requirement_before_the_next_claim(self):
        self.scheduler.claim_post(self.post.schedule_id, "2026-10-01T10:00:00Z")
        self.restart()
        due = self.scheduler.get_due_posts("2026-10-01T10:05:01Z")
        self.assertEqual(len(due), 1)
        self.assertTrue(due[0].provider_state["must_probe"])
        self.assertEqual(due[0].provider_state["uploaded_bytes"], 0)
        self.restart()
        self.assertTrue(self.scheduler.get_post(self.post.schedule_id).provider_state["must_probe"])

    def test_live_claim_is_not_recovered_early(self):
        self.scheduler.claim_post(self.post.schedule_id, "2026-10-01T10:00:00Z")
        self.restart()
        self.assertEqual(self.scheduler.get_due_posts("2026-10-01T10:04:59Z"), [])
        self.assertFalse(self.scheduler.get_post(self.post.schedule_id).provider_state["must_probe"])


if __name__ == "__main__":
    unittest.main()
