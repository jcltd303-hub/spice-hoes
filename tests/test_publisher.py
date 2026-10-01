import os
import shutil
import tempfile
import unittest

from spicecore.core import Store
from spicecore.distribution.mock import MockPublisher
from spicecore.distribution.scheduler import Scheduler, ScheduleStatus
from spicecore.distribution.worker import OutboxWorker
from spicecore.media.models import MediaJob, RenderState


class TestPublisher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_pub.sqlite")
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(store=self.store)
        self.mock_publisher = MockPublisher(platform="mock_social")

        self.worker = OutboxWorker(
            scheduler=self.scheduler,
            publishers={"mock_social": self.mock_publisher},
            store=self.store,
        )

        # Create approved candidate in store
        self.persona = {"id": "lila_hart", "name": "Lila Hart", "version": "5c83ea291410"}
        self.cid = self.store.propose(
            persona=self.persona,
            theme="studio ceramics",
            format="video",
            channel="mock_social",
            offer="Glaze recipe guide",
            cost_cents=20,
        )
        self.store.review(self.cid, "approved", reviewer="lead_operator")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mock_publisher_publishes_exactly_once_and_is_idempotent(self):
        idempotency_key = "test_idem_12345"
        res1 = self.mock_publisher.publish(
            media_uri="/tmp/sample.mp4",
            caption="Fresh pottery on the wheel.",
            disclosure="Fictional character",
            account_id="lila_ceramics",
            idempotency_key=idempotency_key,
        )
        self.assertTrue(res1.success)
        post_id1 = res1.external_post_id

        # Second publish call with same idempotency key
        res2 = self.mock_publisher.publish(
            media_uri="/tmp/sample.mp4",
            caption="Fresh pottery on the wheel.",
            disclosure="Fictional character",
            account_id="lila_ceramics",
            idempotency_key=idempotency_key,
        )
        self.assertTrue(res2.success)
        self.assertEqual(res2.external_post_id, post_id1)
        self.assertEqual(len(self.mock_publisher.published_posts), 1)

    def test_outbox_worker_publishes_due_approved_posts(self):
        job = MediaJob(
            persona_id="lila_hart",
            candidate_id=self.cid,
            source_asset_uri="https://images.unsplash.com/sample_lila.jpg",
            script="Warm clays and peaceful moments in the ceramic studio.",
            status=RenderState.APPROVED,
            output_uri="/tmp/lila_reel.mp4",
        )
        post = self.scheduler.schedule(
            media_job=job,
            platform="mock_social",
            account_id="lila_ceramics",
            scheduled_at_iso="2026-10-01T10:00:00Z",
        )

        # Run outbox worker as of 10:30 (due)
        results = self.worker.process_due(as_of_iso="2026-10-01T10:30:00Z")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(post.status, ScheduleStatus.PUBLISHED)
        self.assertIsNotNone(post.external_post_id)
        self.assertIsNotNone(post.canonical_url)

        # Running worker again does NOT re-publish (idempotency safeguard)
        results_again = self.worker.process_due(as_of_iso="2026-10-01T11:00:00Z")
        self.assertEqual(len(results_again), 0)
        self.assertEqual(len(self.mock_publisher.published_posts), 1)

    def test_outbox_worker_retries_on_failure(self):
        job = MediaJob(
            persona_id="lila_hart",
            candidate_id=self.cid,
            source_asset_uri="https://images.unsplash.com/sample_lila.jpg",
            script="Studio work session.",
            status=RenderState.APPROVED,
            output_uri="/tmp/lila_reel2.mp4",
        )
        post = self.scheduler.schedule(
            media_job=job,
            platform="mock_social",
            account_id="lila_ceramics",
            scheduled_at_iso="2026-10-01T12:00:00Z",
        )

        # Instruct mock publisher to fail the next call with a retryable error
        self.mock_publisher.fail_next = True
        self.mock_publisher.retryable_failure = True

        results = self.worker.process_due(as_of_iso="2026-10-01T12:30:00Z")
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(post.retry_count, 1)
        self.assertEqual(post.status, ScheduleStatus.SCHEDULED)  # Still scheduled for retry

        # Second attempt succeeds
        results2 = self.worker.process_due(as_of_iso="2026-10-01T12:35:00Z")
        self.assertEqual(len(results2), 1)
        self.assertTrue(results2[0].success)
        self.assertEqual(post.status, ScheduleStatus.PUBLISHED)


if __name__ == "__main__":
    unittest.main()
