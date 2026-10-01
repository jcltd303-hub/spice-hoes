import base64
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.masterref import MasterReferenceBuilder, REFERENCE_VIEWS


PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"
    )
).decode()


class FakeProvider:
    model_name = "local-dream:test"

    def __init__(self, scores=None):
        self.generate_calls = []
        self.score_calls = []
        self.scores = iter(scores or [0.95] * 32)

    def generate_image(self, **kwargs):
        self.generate_calls.append(kwargs)
        return {"image_base64": PNG_1X1, "mime_type": "image/png"}

    def score_identity(self, **kwargs):
        self.score_calls.append(kwargs)
        return {"score": next(self.scores), "model": "fake-identity"}


class MasterReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "master.sqlite")
        self.persona = {
            "id": "zara_voss",
            "name": "Zara Voss",
            "age": 29,
            "fictional": True,
            "version": "v1",
            "visual": "short curls, vivid color blocks",
        }

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_build_selects_consensus_anchor_and_best_view_attempts(self):
        provider = FakeProvider()
        builder = MasterReferenceBuilder(
            self.store,
            provider=provider,
            staging_root=Path(self.tmp.name) / "staging",
            reference_root=Path(self.tmp.name) / "refs",
            anchor_candidates=3,
            attempts_per_view=2,
        )
        manifest = builder.build(self.persona, seed=100)
        self.assertEqual(len(manifest["files"]), len(REFERENCE_VIEWS))
        self.assertTrue(manifest["ready_for_promotion"])
        self.assertEqual(len(manifest["anchor_diagnostics"]), 3)
        self.assertEqual(sum(1 for x in manifest["anchor_diagnostics"] if x["selected"]), 1)
        self.assertIsNone(provider.generate_calls[0]["references"])
        self.assertEqual(len(provider.generate_calls[3]["references"]), 1)
        self.assertEqual(
            [c["seed"] for c in provider.generate_calls],
            [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
        )
        # 3 medoid scores + 10 angle-attempt scores
        self.assertEqual(len(provider.score_calls), 13)

    def test_low_identity_view_blocks_promotion(self):
        # Anchor consensus passes; first profile attempts both fail; remaining attempts pass.
        scores = [0.95, 0.96, 0.94, 0.40, 0.50] + [0.95] * 8
        provider = FakeProvider(scores=scores)
        builder = MasterReferenceBuilder(
            self.store,
            provider=provider,
            staging_root=Path(self.tmp.name) / "staging",
            reference_root=Path(self.tmp.name) / "refs",
            identity_threshold=0.84,
            anchor_candidates=3,
            attempts_per_view=2,
        )
        manifest = builder.build(self.persona)
        self.assertFalse(manifest["ready_for_promotion"])
        manifest_path = (
            Path(self.tmp.name) / "staging" / self.persona["id"] /
            manifest["run_id"] / "manifest.json"
        )
        with self.assertRaises(ValueError):
            builder.promote(manifest_path)

    def test_promote_installs_canonical_pack(self):
        provider = FakeProvider()
        refs = Path(self.tmp.name) / "refs"
        builder = MasterReferenceBuilder(
            self.store,
            provider=provider,
            staging_root=Path(self.tmp.name) / "staging",
            reference_root=refs,
            anchor_candidates=3,
            attempts_per_view=1,
        )
        manifest = builder.build(self.persona)
        manifest_path = (
            Path(self.tmp.name) / "staging" / self.persona["id"] /
            manifest["run_id"] / "manifest.json"
        )
        result = builder.promote(manifest_path)
        self.assertEqual(result["file_count"], len(REFERENCE_VIEWS))
        self.assertTrue((refs / self.persona["id"] / "manifest.json").exists())
        self.assertEqual(self.store.events()[-1]["kind"], "master_reference_pack_promoted")


if __name__ == "__main__":
    unittest.main()
