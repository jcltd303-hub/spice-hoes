import base64
import tempfile
import unittest
from pathlib import Path

from spicecore.assetgen import AssetGenerator, build_asset_prompt
from spicecore.core import Store


PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"
    )
).decode()


class FakeProvider:
    model_name = "local-dream:test"

    def __init__(self, identity_score=0.95, quality=None):
        self.calls = []
        self.score_calls = []
        self.identity_score = identity_score
        self.quality = quality or {"anatomy": 0.95, "hands": 0.9, "face_visibility": 0.95, "realism": 0.9, "composition": 0.9}

    def generate_image(self, **kwargs):
        self.calls.append(kwargs)
        return {"image_base64": PNG_1X1, "mime_type": "image/png"}

    def score_identity(self, **kwargs):
        self.score_calls.append(kwargs)
        return {"score": self.identity_score, "model": "fake-identity"}

    def score_quality(self, **kwargs):
        return {**self.quality, "model": "fake-quality"}


class AssetGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "assets.sqlite")
        self.persona = {
            "id": "zara_voss", "name": "Zara Voss", "age": 29,
            "fictional": True, "version": "v1", "visual": "short curls",
            "voice": "direct", "hobbies": ["percussion"],
        }

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_prompt_locks_identity_and_adult_status(self):
        prompt = build_asset_prompt(self.persona, "city nights", "night market")
        self.assertIn("age 29", prompt)
        self.assertIn("same facial proportions", prompt)
        self.assertIn("Do not resemble any real person", prompt)

    def test_generate_without_reference_is_unscored_and_reviewable(self):
        provider = FakeProvider()
        generator = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "generated",
            reference_root=Path(self.tmp.name) / "refs",
            quality_threshold=0.4,
        )
        result = generator.generate(
            self.persona, "city nights", "Instagram", "affiliate", seed=42
        )
        self.assertTrue(Path(result["asset_path"]).exists())
        self.assertTrue(Path(result["metadata_path"]).exists())
        self.assertEqual(self.store.candidate(result["candidate_id"])["status"], "proposed")
        self.assertEqual(provider.calls[0]["seed"], 42)
        self.assertIsNone(provider.calls[0]["references"])
        self.assertFalse(result["identity"]["scored"])
        self.assertEqual(self.store.events()[-1]["kind"], "asset_generated")

    def test_reference_conditioning_and_identity_pass(self):
        root = Path(self.tmp.name) / "refs" / "zara_voss"
        root.mkdir(parents=True)
        (root / "master.png").write_bytes(b"reference-image")
        provider = FakeProvider(identity_score=0.93)
        generator = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "generated",
            reference_root=Path(self.tmp.name) / "refs",
            identity_threshold=0.82,
            quality_threshold=0.4,
        )
        result = generator.generate(self.persona, "city nights", "Instagram", "affiliate")
        self.assertEqual(result["reference_count"], 1)
        self.assertEqual(len(provider.calls[0]["references"]), 1)
        self.assertTrue(result["identity"]["passed"])
        self.assertEqual(result["status"], "proposed")

    def test_off_model_asset_is_rejected_before_review_queue(self):
        root = Path(self.tmp.name) / "refs" / "zara_voss"
        root.mkdir(parents=True)
        (root / "master.png").write_bytes(b"reference-image")
        provider = FakeProvider(identity_score=0.51)
        generator = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "generated",
            reference_root=Path(self.tmp.name) / "refs",
            identity_threshold=0.82,
        )
        result = generator.generate(self.persona, "city nights", "Instagram", "affiliate")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.store.candidate(result["candidate_id"])["status"], "rejected")
        proposed = self.store.db.execute(
            "SELECT COUNT(*) FROM candidates WHERE status='proposed'"
        ).fetchone()[0]
        self.assertEqual(proposed, 0)


    def test_bad_visual_quality_is_rejected_before_review_queue(self):
        provider = FakeProvider(quality={
            "anatomy": 0.2,
            "hands": 0.9,
            "face_visibility": 0.95,
            "realism": 0.95,
            "composition": 0.95,
        })
        generator = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "generated",
            reference_root=Path(self.tmp.name) / "refs",
            quality_threshold=0.4,
        )
        result = generator.generate(self.persona, "city nights", "Instagram", "affiliate")
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["quality"]["passed"])
        self.assertEqual(self.store.candidate(result["candidate_id"])["status"], "rejected")
        self.assertTrue(any(e["kind"] == "quality_checked" for e in self.store.events()))

    def test_batch_derives_deterministic_seeds(self):
        provider = FakeProvider()
        generator = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "generated",
            reference_root=Path(self.tmp.name) / "refs",
            quality_threshold=0.4,
        )
        people = [self.persona, {**self.persona, "id": "tess_wilder", "name": "Tess Wilder"}]
        out = generator.batch(people, "training", "TikTok", "affiliate", count_per_persona=2, seed=100)
        self.assertEqual(len(out), 4)
        self.assertEqual([c["seed"] for c in provider.calls], [100, 101, 1100, 1101])


if __name__ == "__main__":
    unittest.main()
