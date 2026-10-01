import base64
import io
import unittest

from PIL import Image

from spicecore.quality import QualityGate


class FakeProvider:
    def __init__(self, **scores):
        self.scores = {
            "anatomy": 0.95,
            "hands": 0.9,
            "face_visibility": 0.95,
            "realism": 0.9,
            "composition": 0.9,
            **scores,
        }

    def score_quality(self, **kwargs):
        return {**self.scores, "model": "fake-quality"}


def image_bytes(value=128):
    image = Image.new("RGB", (768, 1024), (value, value, value))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class QualityGateTests(unittest.TestCase):
    def test_good_image_passes(self):
        result = QualityGate(FakeProvider(), threshold=0.6).score(image_bytes(), "image/png")
        self.assertTrue(result["passed"])
        self.assertIn("sharpness", result["local"])
        self.assertEqual(result["provider"]["model"], "fake-quality")

    def test_bad_anatomy_fails_even_if_average_is_high(self):
        result = QualityGate(
            FakeProvider(anatomy=0.2, hands=1, face_visibility=1, realism=1, composition=1),
            threshold=0.5,
        ).score(image_bytes(), "image/png")
        self.assertFalse(result["passed"])
        self.assertIn("anatomy", result["reasons"])


if __name__ == "__main__":
    unittest.main()
