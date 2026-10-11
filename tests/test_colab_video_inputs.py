"""Run the notebook input cells against real images and the real ZIP bridge."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from PIL import Image, ImageChops

from spicecore.freegpu import export_job, read_bundle


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/spice_free_gpu_media.ipynb"


class ColabVideoInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cells = json.loads(NOTEBOOK.read_text())["cells"]
        self.image = io.BytesIO()
        Image.new("RGB", (120, 200), "blue").save(self.image, "PNG")

    def run_input(self, uploads, **settings):
        # Colab's browser upload is the only external dependency here.
        # Its file map contains the exact bytes returned by files.upload().
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        scope = {
            "Path": Path, "os": os, "tempfile": tempfile, "json": json,
            "read_bundle": read_bundle,
            "files": types.SimpleNamespace(upload=lambda: uploads),
        }
        controls = next((c for c in self.cells if c.get("id") == "adult-video-controls"), None)
        if controls is not None:
            exec("".join(controls["source"]), scope)
        scope.update(settings)
        cell = next(c for c in self.cells if c.get("id") == "attended-05")
        # Redirect only Colab's fixed output directory into a real test directory.
        code = "".join(cell["source"]).replace('"/content"', repr(str(self.root)))
        code = code.replace('"/content/spice-attended-job.zip"', repr(str(self.root / "spice-attended-job.zip")))
        with contextlib.redirect_stdout(io.StringIO()):
            exec(code, scope)
        return scope

    def test_new_image_creates_an_importable_job_with_selected_seed(self):
        try:
            scope = self.run_input(
                {"portrait.png": self.image.getvalue()},
                JOB_SOURCE="New approved adult image", VIDEO_STYLE="glamour-subtle",
                VIDEO_SEED=123, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=True,
            )
        except ValueError as exc:
            self.fail(f"The new-image input path rejected a valid approved image: {exc}")
        job = read_bundle(scope["JOB_ZIP"], kind="job")
        self.assertEqual(job["task"], "video")
        self.assertEqual(job["options"]["pipeline"], "svd-i2v")
        self.assertEqual(job["options"]["seed"], 123)
        self.assertEqual(job["files"][0]["sha256"], hashlib.sha256(self.image.getvalue()).hexdigest())
        self.assertTrue(job["approved_fictional_persona"])
        self.assertTrue(scope["JOB_CREATED_HERE"])

    def test_uploaded_job_keeps_its_original_bytes_and_options(self):
        image = self.root / "source.png"
        image.write_bytes(self.image.getvalue())
        source = self.root / "original.zip"
        export_job(source, task="video", inputs={"image": image, "prompt": "Gym portrait descriptor"},
                   options={"pipeline": "svd-i2v", "seed": 456, "motion_bucket_id": 80},
                   approved_fictional_persona=True, job_id="existing-controller-job")
        original = source.read_bytes()
        scope = self.run_input(
            {"gym.zip": original}, JOB_SOURCE="Exported job ZIP",
            VIDEO_STYLE="glamour-subtle", VIDEO_SEED=123,
        )
        self.assertEqual(scope["JOB_ZIP"].read_bytes(), original)
        self.assertEqual(scope["job"]["job_id"], "existing-controller-job")
        self.assertEqual(scope["job"]["options"]["seed"], 456)

    def test_new_image_rejects_invalid_seed_before_creating_job(self):
        with self.assertRaisesRegex(ValueError, "seed"):
            self.run_input(
                {"portrait.png": self.image.getvalue()},
                JOB_SOURCE="New approved adult image", VIDEO_STYLE="glamour-subtle",
                VIDEO_SEED=-1, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=True,
            )
        self.assertFalse(list(self.root.glob("*.zip")))

    def test_new_image_requires_explicit_adult_nonexplicit_confirmation(self):
        with self.assertRaises(ValueError):
            self.run_input(
                {"portrait.png": self.image.getvalue()},
                JOB_SOURCE="New approved adult image", VIDEO_STYLE="glamour-subtle",
                VIDEO_SEED=123, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=False,
            )
        self.assertFalse(list(self.root.glob("*.zip")))

    def test_new_image_rejects_unknown_preset_before_creating_job(self):
        with self.assertRaises(ValueError):
            self.run_input(
                {"portrait.png": self.image.getvalue()},
                JOB_SOURCE="New approved adult image", VIDEO_STYLE="unknown-style",
                VIDEO_SEED=123, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=True,
            )
        self.assertFalse(list(self.root.glob("*.zip")))

    def test_reference_preview_uses_phone_jpeg_orientation(self):
        image = Image.new("RGB", (200, 120), "blue")
        exif = image.getexif()
        exif[274] = 6  # Camera metadata: display this landscape storage as a portrait.
        uploaded = io.BytesIO()
        image.save(uploaded, format="JPEG", exif=exif)
        scope = self.run_input(
            {"phone-photo.jpg": uploaded.getvalue()},
            JOB_SOURCE="New approved adult image", VIDEO_STYLE="glamour-subtle",
            VIDEO_SEED=123, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=True,
        )
        frames = []
        display_module = types.ModuleType("IPython.display")
        display_module.display = lambda frame: frames.append(frame.copy())
        cell = next(c for c in self.cells if c.get("id") == "video-input-preview")
        code = "".join(cell["source"]).replace('"/content"', repr(str(self.root)))
        with mock.patch.dict("sys.modules", {"IPython": types.ModuleType("IPython"),
                                             "IPython.display": display_module}):
            exec(code, scope)
        self.assertEqual(len(frames), 1)
        difference = ImageChops.difference(frames[0], Image.new("RGB", (1024, 576), (16, 16, 16)))
        # 120x200 displayed portrait fits to 346x576, centered at x=339.
        self.assertEqual(difference.getbbox(), (339, 0, 685, 576))

    def test_invalid_seed_can_be_corrected_without_restarting_runtime(self):
        settings = {"JOB_SOURCE": "New approved adult image", "VIDEO_STYLE": "glamour-subtle",
                    "APPROVED_FICTIONAL_ADULT_NONEXPLICIT": True}
        with self.assertRaisesRegex(ValueError, "seed"):
            self.run_input({"portrait.png": self.image.getvalue()}, VIDEO_SEED=-1, **settings)
        try:
            scope = self.run_input({"portrait.png": self.image.getvalue()}, VIDEO_SEED=123, **settings)
        except RuntimeError as exc:
            self.fail(f"A rejected input should not block a corrected retry: {exc}")
        self.assertEqual(read_bundle(scope["JOB_ZIP"], kind="job")["options"]["seed"], 123)

    def test_accidental_input_rerun_keeps_original_job_download_available(self):
        scope = self.run_input(
            {"portrait.png": self.image.getvalue()},
            JOB_SOURCE="New approved adult image", VIDEO_STYLE="glamour-subtle",
            VIDEO_SEED=123, APPROVED_FICTIONAL_ADULT_NONEXPLICIT=True,
        )
        original = scope["JOB_ZIP"].read_bytes()
        cell = next(c for c in self.cells if c.get("id") == "attended-05")
        code = "".join(cell["source"]).replace('"/content"', repr(str(self.root)))
        code = code.replace('"/content/spice-attended-job.zip"', repr(str(self.root / "spice-attended-job.zip")))
        with self.assertRaises(RuntimeError):
            exec(code, scope)
        self.assertTrue(scope["JOB_CREATED_HERE"])
        self.assertEqual(scope["JOB_ZIP"].read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
