import base64
import unittest

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


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"
)


def image_bytes(value=128):
    return PNG_1X1


class QualityGateTests(unittest.TestCase):
    def test_good_image_passes(self):
        result = QualityGate(FakeProvider(), threshold=0.6).score(image_bytes(), "image/png")
        self.assertTrue(result["passed"])
        self.assertIn("sharpness", result["local"])
        self.assertIn("available", result["local"])
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
