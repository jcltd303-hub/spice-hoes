import base64
import tempfile
import unittest
from pathlib import Path

from spicecore.assetgen import AssetGenerator
from spicecore.core import Store
from spicecore.quality_assetgen import QualityAssetGenerator


PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"
    )
).decode()


class FakeProvider:
    model_name = "local-dream:test"

    def __init__(self, quality=None):
        self.quality = quality or {
            "anatomy": 0.95,
            "hands": 0.9,
            "face_visibility": 0.95,
            "realism": 0.9,
            "composition": 0.9,
        }

    def generate_image(self, **kwargs):
        return {"image_base64": PNG_1X1, "mime_type": "image/png"}

    def score_quality(self, **kwargs):
        return {**self.quality, "model": "fake-quality"}


class QualityAssetGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "qa.sqlite")
        self.persona = {
            "id": "zara_voss",
            "name": "Zara Voss",
            "age": 29,
            "fictional": True,
            "version": "v1",
            "visual": "short curls",
            "voice": "direct",
            "hobbies": ["percussion"],
        }

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def build(self, provider, threshold=0.4):
        base = AssetGenerator(
            self.store,
            provider=provider,
            asset_dir=Path(self.tmp.name) / "assets",
            reference_root=Path(self.tmp.name) / "refs",
        )
        return QualityAssetGenerator(base, quality_threshold=threshold)

    def test_quality_pass_keeps_candidate_proposed(self):
        result = self.build(FakeProvider()).generate(
            self.persona, "city nights", "Instagram", "affiliate"
        )
        self.assertEqual(result["status"], "proposed")
        self.assertTrue(result["quality"]["passed"])
        self.assertEqual(self.store.events()[-1]["kind"], "quality_checked")

    def test_quality_failure_auto_rejects(self):
        provider = FakeProvider({
            "anatomy": 0.2,
            "hands": 0.9,
            "face_visibility": 0.95,
            "realism": 0.95,
            "composition": 0.95,
        })
        result = self.build(provider, threshold=0.4).generate(
            self.persona, "city nights", "Instagram", "affiliate"
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(self.store.candidate(result["candidate_id"])["status"], "rejected")
        self.assertIn("anatomy", result["quality"]["reasons"])


if __name__ == "__main__":
    unittest.main()
