import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/test-local-dream-image.sh"


class LocalDreamRealismScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for persona in ("celeste_vale", "zara_voss"):
            dest = self.root / "data/references" / persona
            dest.mkdir(parents=True)
            shutil.copy2(REPO / "data/references" / persona / "canon-01.png", dest)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("SPICE_", "LOCAL_DREAM_"))}
        self.env["SPICE_HOES_DIR"] = str(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_dry_run_is_a_single_persona_local_dream_candidate(self):
        result = self.run_script("celeste_vale", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertEqual(request["generator"], "local-dream")
        self.assertEqual(request["persona_id"], "celeste_vale")
        self.assertEqual(request["style"], "photo-test")
        self.assertEqual((request["steps"], request["guidance"], request["seed"]),
                         (24, 5.5, 41000))
        self.assertEqual(request["best_of_n"], 1)
        self.assertTrue(request["require_persona_bank"])
        self.assertIn("cartoon", request["negative_prompt"])
        self.assertFalse((self.root / "data/runs").exists())

    def test_dry_run_preserves_overridden_settings_and_json_scene(self):
        self.env.update(SPICE_TEST_STEPS="28", SPICE_TEST_GUIDANCE="6", SPICE_TEST_SEED="72",
                        SPICE_TEST_SCENE='gray wall, "quiet" morning')
        result = self.run_script("zara_voss", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertEqual((request["steps"], request["guidance"], request["seed"]), (28, 6, 72))
        self.assertEqual(request["scene"], 'gray wall, "quiet" morning')

    def test_legacy_image_cannot_replace_missing_canon(self):
        dest = self.root / "data/references/celeste_vale"
        (dest / "canon-01.png").rename(dest / "bootstrap-1.png")
        result = self.run_script("celeste_vale", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canon", result.stderr.lower())

    def test_unknown_persona_is_rejected(self):
        result = self.run_script("../other", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("persona", result.stderr.lower())
