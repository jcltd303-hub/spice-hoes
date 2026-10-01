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

    def __init__(self):
        self.calls = []

    def generate_image(self, **kwargs):
        self.calls.append(kwargs)
        return {"image_base64": PNG_1X1, "mime_type": "image/png"}


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

    def test_generate_persists_asset_and_creates_review_candidate(self):
        provider = FakeProvider()
        generator = AssetGenerator(
            self.store, provider=provider, asset_dir=Path(self.tmp.name) / "generated"
        )
        result = generator.generate(
            self.persona, "city nights", "Instagram", "affiliate", seed=42
        )
        self.assertTrue(Path(result["asset_path"]).exists())
        self.assertTrue(Path(result["metadata_path"]).exists())
        self.assertEqual(self.store.candidate(result["candidate_id"])["status"], "proposed")
        self.assertEqual(provider.calls[0]["seed"], 42)
        self.assertEqual(self.store.events()[-1]["kind"], "asset_generated")

    def test_batch_derives_deterministic_seeds(self):
        provider = FakeProvider()
        generator = AssetGenerator(
            self.store, provider=provider, asset_dir=Path(self.tmp.name) / "generated"
        )
        people = [self.persona, {**self.persona, "id": "tess_wilder", "name": "Tess Wilder"}]
        out = generator.batch(people, "training", "TikTok", "affiliate", count_per_persona=2, seed=100)
        self.assertEqual(len(out), 4)
        self.assertEqual([c["seed"] for c in provider.calls], [100, 101, 1100, 1101])


if __name__ == "__main__":
    unittest.main()
