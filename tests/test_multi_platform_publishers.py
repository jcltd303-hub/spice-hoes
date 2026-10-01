import unittest
from spicecore.distribution.mock import MockPublisher
from spicecore.distribution.tiktok import TikTokPublisher
from spicecore.distribution.youtube import YouTubeShortsPublisher
from spicecore.distribution.scheduler import Scheduler, ScheduleStatus
from spicecore.distribution.worker import OutboxWorker
from spicecore.media.models import MediaJob, RenderState


class TestMultiPlatformPublishers(unittest.TestCase):
    def setUp(self):
        self.tiktok_pub = TikTokPublisher(access_token="")
        self.youtube_pub = YouTubeShortsPublisher(access_token="")

    def test_tiktok_publisher_fails_closed_without_credentials(self):
        res = self.tiktok_pub.publish(
            media_uri="https://cdn.example.com/zara_clip.mp4",
            caption="Bassline in the underground.",
            disclosure="Fictional character",
            account_id="zara_voss_official",
            idempotency_key="tt_key_001",
        )
        self.assertFalse(res.success)
        self.assertFalse(res.retryable)
        self.assertIn("TIKTOK_ACCESS_TOKEN", res.error_message)
        with self.assertRaises(RuntimeError):
            self.tiktok_pub.fetch_metrics("missing", "zara_voss_official")

    def test_youtube_shorts_publisher_fails_closed_without_credentials(self):
        res = self.youtube_pub.publish(
            media_uri="https://cdn.example.com/tess_clip.mp4",
            caption="Morning summit workout.",
            disclosure="Fictional character",
            account_id="tess_wilder",
            idempotency_key="yt_key_001",
        )
        self.assertFalse(res.success)
        self.assertFalse(res.retryable)
        self.assertIn("YOUTUBE_ACCESS_TOKEN", res.error_message)
        with self.assertRaises(RuntimeError):
            self.youtube_pub.fetch_metrics("missing", "tess_wilder")

    def test_outbox_worker_uses_explicit_mock_publishers_for_tests(self):
        scheduler = Scheduler()
        worker = OutboxWorker(
            scheduler=scheduler,
            publishers={
                "tiktok": MockPublisher(platform="tiktok"),
                "youtube_shorts": MockPublisher(platform="youtube_shorts"),
            }
        )

        job1 = MediaJob(
            persona_id="zara_voss",
            candidate_id="cand_1",
            source_asset_uri="https://cdn.example.com/zara.jpg",
            script="Zara clip on TikTok",
            status=RenderState.APPROVED,
            output_uri="/tmp/zara.mp4",
        )
        job2 = MediaJob(
            persona_id="tess_wilder",
            candidate_id="cand_2",
            source_asset_uri="https://cdn.example.com/tess.jpg",
            script="Tess clip on Shorts",
            status=RenderState.APPROVED,
            output_uri="/tmp/tess.mp4",
        )

        p1 = scheduler.schedule(job1, "tiktok", "zara_tt", "2026-10-01T12:00:00Z")
        p2 = scheduler.schedule(job2, "youtube_shorts", "tess_yt", "2026-10-01T12:00:00Z")

        results = worker.process_due("2026-10-01T12:05:00Z")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(p1.status, ScheduleStatus.PUBLISHED)
        self.assertEqual(p2.status, ScheduleStatus.PUBLISHED)


if __name__ == "__main__":
    unittest.main()
