import base64
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from spicecore.core import Store
from spicecore.identity_master import (
    CENTER_VIEW,
    PORTRAIT_VIEWS,
    ROTATION_VIEWS,
    build_master_prompts,
    composite_portrait_board,
    generate_master_views,
    promote_master,
)


PERSONA = {
    "id": "zara_voss",
    "version": 3,
    "name": "Zara Voss",
    "age": 29,
    "fictional": True,
    "visual": "short dark curls, strong brows, amber-brown eyes",
    "physical": {
        "eye_color": "amber-brown",
        "eye_shape": "almond",
        "hair_color": "dark espresso brown",
        "distinguishing_features": ["asymmetric left brow"],
    },
    "identity_reference": {
        "body_prompt": "lithe athletic adult woman",
        "wardrobe_mode": "neutral minimal reference clothing",
        "hair_mode": "hair pulled up tightly",
    },
}

ALL_VIEWS = [v for v, _ in PORTRAIT_VIEWS] + [CENTER_VIEW[0]] + [v for v, _ in ROTATION_VIEWS]


def _solid_png(color, size=(64, 64)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class FakeMediaProvider:
    model_name = "fake:media"

    def __init__(self, score=0.9):
        self.score_value = score
        self.calls = []

    def generate_image(self, prompt, negative_prompt="", seed=None,
                       width=1024, height=1024, references=None,
                       reference_strength=0.85):
        self.calls.append({"prompt": prompt, "seed": seed, "width": width, "height": height})
        color = (seed or 0) % 256, 100, 150
        return {"image_base64": base64.b64encode(_solid_png(color, (width, height))).decode("ascii")}

    def score_identity(self, image_base64, image_mime_type, references):
        return {"score": self.score_value, "metric": "cosine", "model": "fake"}


class IdentityMasterTests(unittest.TestCase):
    def test_prompts_cover_all_views(self):
        prompts = build_master_prompts(PERSONA)
        self.assertEqual(sorted(prompts), sorted(ALL_VIEWS))
        self.assertEqual(len(prompts), 9)

    def test_prompts_carry_identity_anchor(self):
        prompts = build_master_prompts(PERSONA)
        body = prompts["portrait_front"]
        self.assertIn("Zara Voss", body)
        self.assertIn("amber-brown", body)
        self.assertIn("neutral minimal reference clothing", body)
        self.assertIn("asymmetric left brow", body)

    def test_refuses_non_fictional_or_underage(self):
        with self.assertRaises(ValueError):
            build_master_prompts({**PERSONA, "fictional": False})
        with self.assertRaises(ValueError):
            build_master_prompts({**PERSONA, "age": 16})
        with self.assertRaises(ValueError):
            build_master_prompts({"id": "x", "age": 30})  # not fictional

    def test_generate_master_views(self):
        provider = FakeMediaProvider()
        views = generate_master_views(provider, PERSONA, seed=42, size=256)
        self.assertEqual(sorted(views), sorted(ALL_VIEWS))
        self.assertEqual(len(provider.calls), 9)
        seeds = [c["seed"] for c in provider.calls]
        self.assertEqual(seeds, list(range(42, 51)))  # deterministic per-view offsets
        body_call = next(c for c in provider.calls if c["width"] != c["height"])
        self.assertLess(body_call["width"], body_call["height"])  # portrait orientation

    def test_composite_board_geometry(self):
        views = {
            "portrait_front": _solid_png((255, 0, 0)),
            "portrait_left34": _solid_png((0, 255, 0)),
            "portrait_right34": _solid_png((0, 0, 255)),
            "portrait_smile": _solid_png((255, 255, 0)),
            "eye_closeup": _solid_png((255, 255, 255)),
        }
        board = composite_portrait_board(views, cell=100, eye_size=40)
        self.assertEqual(board.size, (200, 200))
        px = board.load()
        self.assertEqual(px[10, 10], (255, 0, 0))      # top-left: front
        self.assertEqual(px[190, 10], (0, 255, 0))     # top-right: left34
        self.assertEqual(px[10, 190], (0, 0, 255))     # bottom-left: right34
        self.assertEqual(px[190, 190], (255, 255, 0))  # bottom-right: smile
        self.assertEqual(px[100, 100], (255, 255, 255))  # dead center: eye

    def test_composite_requires_all_views(self):
        with self.assertRaises(ValueError):
            composite_portrait_board({"portrait_front": _solid_png((0, 0, 0))})

    def test_promote_splits_and_records(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "im.sqlite")
        try:
            provider = FakeMediaProvider(score=0.95)
            views = {v: _solid_png((10, 20, 30)) for v in ALL_VIEWS}
            board = composite_portrait_board(
                {k: views[k] for k in views if k in
                 [v for v, _ in PORTRAIT_VIEWS] + [CENTER_VIEW[0]]},
                cell=32, eye_size=16,
            )
            ref_root = Path(tmp.name) / "references"
            record = promote_master(store, provider, PERSONA, views, board,
                                    reference_root=ref_root, identity_threshold=0.82)
            # No reference pack exists yet -> nothing scored -> all conditioning.
            self.assertEqual(record["conditioning"], sorted(ALL_VIEWS))
            self.assertEqual(record["gate"], [])
            self.assertTrue((ref_root / "zara_voss" / "boards" / "portrait_board.png").exists())
            kinds = [e["kind"] for e in store.events()]
            self.assertIn("identity_master_promoted", kinds)
            self.assertEqual(kinds.count("identity_master_view_scored"), 9)
        finally:
            store.close(); tmp.cleanup()

    def test_promote_gates_passing_views(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "im2.sqlite")
        try:
            ref_root = Path(tmp.name) / "references"
            pack_dir = ref_root / "zara_voss"
            pack_dir.mkdir(parents=True)
            (pack_dir / "ref.png").write_bytes(_solid_png((1, 2, 3)))
            provider = FakeMediaProvider(score=0.95)
            views = {v: _solid_png((10, 20, 30)) for v in ALL_VIEWS}
            board = composite_portrait_board(
                {k: views[k] for k in views if k in
                 [v for v, _ in PORTRAIT_VIEWS] + [CENTER_VIEW[0]]},
                cell=32, eye_size=16,
            )
            record = promote_master(store, provider, PERSONA, views, board,
                                    reference_root=ref_root, identity_threshold=0.82)
            self.assertEqual(record["gate"], sorted(ALL_VIEWS))
            self.assertTrue((ref_root / "zara_voss" / "gate" / "portrait_front.png").exists())
        finally:
            store.close(); tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
