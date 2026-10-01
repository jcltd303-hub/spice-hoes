import os
import shutil
import tempfile
import unittest

from spicecore.core import Store
from spicecore.distribution.scheduler import Scheduler, ScheduleStatus
from spicecore.media.models import MediaJob, RenderState


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_sched.sqlite")
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(store=self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_job(self, status: RenderState) -> MediaJob:
        return MediaJob(
            persona_id="tess_wilder",
            candidate_id="cand_123",
            source_asset_uri="https://images.unsplash.com/sample_tess.jpg",
            script="Climbing requires full concentration. Step by step.",
            status=status,
            output_uri="/tmp/test_tess_video.mp4",
        )

    def test_review_gate_blocks_unapproved_media(self):
        # 1. Proposed content cannot be scheduled
        job_proposed = self._make_job(RenderState.PLANNED)
        with self.assertRaises(PermissionError):
            self.scheduler.schedule(job_proposed, "instagram", "tess_official", "2026-10-01T12:00:00Z")

        # 2. Review ready content cannot be scheduled without human approval
        job_ready = self._make_job(RenderState.REVIEW_READY)
        with self.assertRaises(PermissionError):
            self.scheduler.schedule(job_ready, "instagram", "tess_official", "2026-10-01T12:00:00Z")

        # 3. Rejected content cannot be scheduled
        job_rejected = self._make_job(RenderState.REJECTED)
        with self.assertRaises(PermissionError):
            self.scheduler.schedule(job_rejected, "instagram", "tess_official", "2026-10-01T12:00:00Z")

        # 4. Revise content cannot be scheduled
        job_revise = self._make_job(RenderState.REVISE)
        with self.assertRaises(PermissionError):
            self.scheduler.schedule(job_revise, "instagram", "tess_official", "2026-10-01T12:00:00Z")

    def test_approved_media_schedules_successfully(self):
        job_approved = self._make_job(RenderState.APPROVED)
        post = self.scheduler.schedule(
            media_job=job_approved,
            platform="instagram",
            account_id="tess_official",
            scheduled_at_iso="2026-10-01T15:00:00Z",
            caption="Training season begins. Focus.",
        )
        self.assertEqual(post.status, ScheduleStatus.SCHEDULED)
        self.assertEqual(job_approved.status, RenderState.SCHEDULED)
        self.assertEqual(post.platform, "instagram")
        self.assertEqual(post.account_id, "tess_official")

        # Check due posts filtering
        due_earlier = self.scheduler.get_due_posts(as_of_iso="2026-10-01T14:00:00Z")
        self.assertEqual(len(due_earlier), 0)

        due_later = self.scheduler.get_due_posts(as_of_iso="2026-10-01T15:30:00Z")
        self.assertEqual(len(due_later), 1)
        self.assertEqual(due_later[0].schedule_id, post.schedule_id)

    def test_cancel_scheduled_post(self):
        job_approved = self._make_job(RenderState.APPROVED)
        post = self.scheduler.schedule(job_approved, "instagram", "tess_official", "2026-10-01T18:00:00Z")
        cancelled = self.scheduler.cancel(post.schedule_id)
        self.assertEqual(cancelled.status, ScheduleStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
