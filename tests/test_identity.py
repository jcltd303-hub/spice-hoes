import base64
import tempfile
import unittest
from pathlib import Path

from spicecore.identity import IdentityGate, load_reference_pack


class FakeProvider:
    def __init__(self, score=0.91):
        self.score = score
        self.calls = []

    def score_identity(self, **kwargs):
        self.calls.append(kwargs)
        return {"score": self.score, "model": "fake-identity"}


class IdentityTests(unittest.TestCase):
    def test_reference_pack_loads_images_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "zara_voss"
            root.mkdir()
            (root / "a.png").write_bytes(b"png")
            (root / "b.txt").write_text("skip")
            refs = load_reference_pack("zara_voss", tmp)
            self.assertEqual(len(refs), 1)
            self.assertEqual(base64.b64decode(refs[0]["base64"]), b"png")

    def test_identity_gate_pass_and_fail(self):
        refs = [{"base64": base64.b64encode(b"ref").decode(), "mime_type": "image/png"}]
        passing = IdentityGate(FakeProvider(0.9), threshold=0.82).score(b"gen", "image/png", refs)
        failing = IdentityGate(FakeProvider(0.5), threshold=0.82).score(b"gen", "image/png", refs)
        self.assertTrue(passing["passed"])
        self.assertFalse(failing["passed"])

    def test_no_refs_fails_closed(self):
        result = IdentityGate(FakeProvider(), threshold=0.8).score(b"gen", "image/png", [])
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "no_reference_pack")


if __name__ == "__main__":
    unittest.main()
