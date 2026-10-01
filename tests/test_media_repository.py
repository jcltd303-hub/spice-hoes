import os
import shutil
import tempfile
import unittest

from spicecore.core import Store
from spicecore.media.models import MediaJob, RenderState
from spicecore.media.repository import MediaJobRepository


class MediaJobRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.temp_dir, "media.sqlite"))
        self.repo = MediaJobRepository(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_media_job_survives_repository_reload(self):
        created = self.repo.create(
            persona_id="zara_voss",
            candidate_id="cand_1",
            source_asset_uri="file:///tmp/source.png",
            script="hello",
            aspect_ratio="9:16",
        )
        second = MediaJobRepository(self.store)
        loaded = second.get(created["id"])
        self.assertEqual(loaded.id, created["id"])
        self.assertEqual(loaded.status, RenderState.PLANNED)
        self.assertEqual(second.list()[0]["id"], created["id"])

    def test_review_requires_review_ready_and_persists_decision(self):
        created = self.repo.create(
            persona_id="zara_voss",
            candidate_id="cand_2",
            source_asset_uri="file:///tmp/source.png",
            script="review me",
        )
        with self.assertRaises(ValueError):
            self.repo.review(created["id"], "approved", "operator")

        job = self.repo.get(created["id"])
        job.update_status(RenderState.REVIEW_READY)
        self.repo.save(job)

        reviewed = self.repo.review(created["id"], "approved", "operator", "looks good")
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["reviewer"], "operator")
        self.assertEqual(MediaJobRepository(self.store).get(created["id"]).status, RenderState.APPROVED)


if __name__ == "__main__":
    unittest.main()
