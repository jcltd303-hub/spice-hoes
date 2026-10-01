import os
import shutil
import tempfile
import unittest

from spicecore.core import Store
from spicecore.media.models import MediaJob, RenderState
from spicecore.media.pipeline import MediaPipeline
from spicecore.media.providers.lipsync import MockLipSyncProvider
from spicecore.media.providers.video import MockVideoProvider
from spicecore.media.providers.voice import MockVoiceProvider


class TestMediaPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_exp.sqlite")
        self.store = Store(self.db_path)
        self.output_dir = os.path.join(self.temp_dir, "rendered_output")

        self.pipeline = MediaPipeline(
            store=self.store,
            video_provider=MockVideoProvider(),
            voice_provider=MockVoiceProvider(),
            lipsync_provider=MockLipSyncProvider(),
            output_dir=self.output_dir,
        )

        # Propose and approve a candidate still in store
        self.persona = {
            "id": "zara_voss",
            "name": "Zara Voss",
            "version": "9f84a1e94812",
        }
        self.cid = self.store.propose(
            persona=self.persona,
            theme="night market percussion",
            format="still",
            channel="Instagram",
            offer="VIP soundcheck pass",
            asset_uri="https://images.unsplash.com/sample.jpg",
            prompt="Zara Voss candid percussion performance",
            cost_cents=15,
        )
        self.store.review(self.cid, "approved", reviewer="lead_operator", note="High quality still")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_render_and_review(self):
        # 1. Create Job in PLANNED state
        job = self.pipeline.create_job(
            persona_id="zara_voss",
            candidate_id=self.cid,
            source_asset_uri="https://images.unsplash.com/sample.jpg",
            script="Night markets bring the city to life. The rhythm never stops when the street lights turn on. Tap link for backstage guest list.",
            aspect_ratio="9:16",
            offer="VIP pass",
            cta="Tap link for soundcheck access",
        )
        self.assertEqual(job.status, RenderState.PLANNED)

        # 2. Render Job through state machine to REVIEW_READY
        rendered_job = self.pipeline.render(job)

        self.assertEqual(rendered_job.status, RenderState.REVIEW_READY)
        self.assertIsNotNone(rendered_job.output_uri)
        self.assertTrue(os.path.exists(rendered_job.output_uri))
        self.assertTrue(rendered_job.qa_report.passed)
        self.assertGreater(rendered_job.duration_seconds, 10.0)

        # Cost tracking checks
        self.assertGreater(rendered_job.costs.video_generation_cents, 0)
        self.assertGreater(rendered_job.costs.voice_generation_cents, 0)
        self.assertGreater(rendered_job.costs.render_cents, 0)
        self.assertEqual(rendered_job.render_cost_cents, rendered_job.costs.render_cents)

        # 3. Human Review Gate
        reviewed_job = self.pipeline.review(
            job=rendered_job,
            decision="approved",
            reviewer="operator_sarah",
            note="Flawless vertical 9:16 clip and voice pacing.",
        )
        self.assertEqual(reviewed_job.status, RenderState.APPROVED)
        self.assertEqual(reviewed_job.reviewer, "operator_sarah")

        # 4. Audit trail events in store
        events = self.store.events()
        event_kinds = [e["kind"] for e in events]
        self.assertIn("media_job_created", event_kinds)
        self.assertIn("voice_generated", event_kinds)
        self.assertIn("video_generation_completed", event_kinds)
        self.assertIn("render_completed", event_kinds)
        self.assertIn("video_qa_completed", event_kinds)
        self.assertIn("media_review_ready", event_kinds)
        self.assertIn("asset_reviewed", event_kinds)

    def test_review_gate_rejection_and_revision(self):
        job = self.pipeline.create_job(
            persona_id="zara_voss",
            candidate_id=self.cid,
            source_asset_uri="https://images.unsplash.com/sample.jpg",
            script="Sample script line.",
        )
        rendered_job = self.pipeline.render(job)
        self.assertEqual(rendered_job.status, RenderState.REVIEW_READY)

        # Test rejection
        self.pipeline.review(rendered_job, decision="rejected", reviewer="operator_john", note="Not on brand")
        self.assertEqual(rendered_job.status, RenderState.REJECTED)


if __name__ == "__main__":
    unittest.main()
