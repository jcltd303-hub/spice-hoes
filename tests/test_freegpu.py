"""The batch bridge must preserve real files and reject unsafe/unrelated bundles."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import wave
import zipfile

try:
    from spicecore import freegpu
except ImportError:
    freegpu = None


ROOT = Path(__file__).resolve().parents[1]


class FreeGPUBridgeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(freegpu, "Task 3 needs the freegpu bridge module")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / "private-source.wav"
        with wave.open(str(self.audio), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0\0" * 160)
        self.job = self.root / "job.zip"

    def export(self, **overrides):
        args = {"task": "transcribe", "inputs": {"audio": self.audio}}
        args.update(overrides)
        return freegpu.export_job(self.job, **args)

    def rewrite(self, source, destination, mutate=None, extras=()):
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w") as dst:
            for info in src.infolist():
                data = src.read(info)
                if mutate:
                    data = mutate(info.filename, data)
                dst.writestr(info, data)
            for name, data in extras:
                dst.writestr(name, data)
        return destination

    def result(self, status="completed"):
        self.export()
        result = self.root / "result.zip"
        if status == "pending":
            freegpu.write_result(self.job, result, status=status, blocker="CUDA unavailable")
        else:
            artifact = self.root / "transcript.json"
            artifact.write_text('{"text":"Hello","segments":[]}', encoding="utf-8")
            freegpu.write_result(self.job, result, artifacts={"transcript.json": artifact})
        return result

    def test_roundtrip_preserves_input_hash_and_imports_artifact(self):
        result = self.result()
        manifest = freegpu.read_bundle(self.job, kind="job")
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["inputs"]["audio"], "inputs/audio.wav")
        self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(self.audio.read_bytes()).hexdigest())
        self.assertNotIn("private-source", json.dumps(manifest))
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "imported")
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["cost_cents"], 0)
        self.assertEqual(outcome["job_id"], manifest["job_id"])
        self.assertEqual(len(outcome["artifact_paths"]), 1)
        self.assertEqual(outcome.get("artifacts"), {"transcript.json": outcome["artifact_paths"][0]})
        self.assertEqual(json.loads(Path(outcome["artifact_paths"][0]).read_text())["text"], "Hello")

    def test_pending_import_has_blocker_and_no_artifacts(self):
        result = self.result("pending")
        destination = self.root / "not-created"
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=destination)
        self.assertEqual(outcome["status"], "pending")
        self.assertEqual(outcome["cost_cents"], 0)
        self.assertEqual(outcome["artifact_paths"], [])
        self.assertEqual(outcome.get("artifacts"), {})
        self.assertIn("CUDA", outcome["blocker"])
        self.assertFalse(destination.exists())

    def test_all_tasks_have_explicit_finite_inputs(self):
        image = self.root / "persona.png"
        image.write_bytes(b"explicit approved persona")
        video = self.root / "persona.mp4"
        video.write_bytes(b"explicit approved clip")
        cases = [
            ("video", {"prompt": "Fictional adult walking"}, {}),
            ("video", {"prompt": "Fictional adult walking", "image": image},
             {"pipeline": "cogvideox-i2v", "model": "zai-org/CogVideoX-5b-I2V"}),
            ("video", {"prompt": "Fictional adult walking", "image": image}, {"pipeline": "svd-i2v"}),
            ("tts", {"text": "Hello world"}, {}),
            ("transcribe", {"audio": self.audio}, {}),
            ("lipsync", {"video": video, "audio": self.audio}, {}),
        ]
        for index, (task, inputs, options) in enumerate(cases):
            with self.subTest(task=task, inputs=list(inputs)):
                path = self.root / (task + "-" + str(index) + ".zip")
                manifest = freegpu.export_job(path, task=task, inputs=inputs, options=options,
                                              approved_fictional_persona=True)
                self.assertEqual(freegpu.read_bundle(path, kind="job")["task"], task)
                self.assertGreater(manifest["options"]["timeout_seconds"], 0)

    def test_rejects_bad_task_missing_input_or_unbounded_options(self):
        cases = [
            {"task": "training"}, {"inputs": {}},
            {"task": "tts", "inputs": {"text": " "}},
            {"task": "video", "inputs": {"prompt": "hello"}, "options": {"frames": 999}},
            {"task": "video", "inputs": {"prompt": "hello"}, "options": {"frames": 18}},
            {"task": "video", "inputs": {"prompt": "hello"}, "options": {"width": 1920}},
            {"task": "video", "inputs": {"prompt": "hello"}, "options": {"width": 720.0}},
            {"options": {"timeout_seconds": 0}}, {"options": {"max_seconds": float("inf")}},
            {"options": {"timeout_seconds": 10**1000}},
            {"options": {"command": "curl example.com"}},
            {"inputs": {"audio": "https://example.com/source.wav"}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises((ValueError, OSError)):
                self.export(**case)
        self.assertFalse(self.job.exists())

    def test_requires_explicit_persona_asset_approval(self):
        image = self.root / "persona.png"
        image.write_bytes(b"asset")
        with self.assertRaisesRegex(ValueError, "approved"):
            self.export(task="video", inputs={"prompt": "Hello", "image": image},
                        options={"pipeline": "cogvideox-i2v", "model": "zai-org/CogVideoX-5b-I2V"})

    def test_rejects_source_symlink_and_symlinked_parent(self):
        link = self.root / "linked.wav"
        link.symlink_to(self.audio)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.export(inputs={"audio": link})
        folder = self.root / "linked-dir"
        folder.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.export(inputs={"audio": folder / self.audio.name})

    def test_rejects_traversal_absolute_and_windows_zip_paths_before_extracting(self):
        self.export()
        for name in ("../escape.txt", "/escape.txt", "inputs/../../escape", "C:/escape", "inputs\\escape", "inputs//escape"):
            with self.subTest(name=name):
                bad = self.rewrite(self.job, self.root / "bad.zip", extras=[(name, b"escape")])
                with self.assertRaises(ValueError):
                    freegpu.extract_job(bad, self.root / "extracted")
                self.assertFalse((self.root / "extracted").exists())

    def test_rejects_zip_symlink_and_duplicate_entries(self):
        self.export()
        info = zipfile.ZipInfo("inputs/link.wav")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for extra in ([(info, b"/etc/passwd")], [("manifest.json", b"{}")]):
                bad = self.rewrite(self.job, self.root / "bad.zip", extras=extra)
                with self.assertRaises(ValueError):
                    freegpu.read_bundle(bad, kind="job")

    def test_rejects_entry_count_size_and_compression_bombs(self):
        self.export()
        bad = self.rewrite(self.job, self.root / "many.zip",
                           extras=[(f"inputs/{i}.wav", b"x") for i in range(40)])
        with self.assertRaisesRegex(ValueError, "limit|entries"):
            freegpu.read_bundle(bad, kind="job")
        bomb = self.root / "bomb.zip"
        with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", b"{}")
            archive.writestr("inputs/bomb.wav", b"0" * (2 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "ratio|compression"):
            freegpu.read_bundle(bomb, kind="job")
        with zipfile.ZipFile(bomb, "w") as archive:
            archive.writestr("manifest.json", b" " * (65 * 1024))
        with self.assertRaisesRegex(ValueError, "limit|size"):
            freegpu.read_bundle(bomb, kind="job")

    def test_rejects_missing_payload_and_duplicate_json_keys(self):
        self.export()
        bad = self.root / "missing.zip"
        with zipfile.ZipFile(self.job) as original, zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("manifest.json", original.read("manifest.json"))
        with self.assertRaisesRegex(ValueError, "missing"):
            freegpu.read_bundle(bad, kind="job")
        bad = self.rewrite(self.job, self.root / "keys.zip",
                           mutate=lambda name, data: data.replace(b'"version":1', b'"version":1,"version":1')
                           if name == "manifest.json" else data)
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            freegpu.read_bundle(bad, kind="job")

    def test_entry_limit_is_checked_before_allocating_the_zip_directory(self):
        from unittest import mock
        self.export()
        bad = self.rewrite(self.job, self.root / "many.zip",
                           extras=[(f"inputs/{i}.wav", b"x") for i in range(40)])
        # The central directory must not be parsed into unbounded ZipInfo
        # objects first. A hostile archive can hold millions of tiny entries.
        with mock.patch("spicecore.freegpu.zipfile.ZipFile", side_effect=AssertionError("Unbounded directory parsed")):
            with self.assertRaisesRegex(ValueError, "entries|limit"):
                freegpu.read_bundle(bad, kind="job")

    def test_valid_job_extracts_only_explicit_inputs(self):
        self.export()
        destination = self.root / "extracted"
        manifest = freegpu.extract_job(self.job, destination)
        self.assertEqual((destination / manifest["inputs"]["audio"]).read_bytes(), self.audio.read_bytes())
        self.assertEqual([p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()],
                         ["inputs/audio.wav"])

    def test_exports_to_filesystems_without_hardlinks(self):
        from unittest import mock
        # Android shared storage commonly denies hardlinks. The portable
        # fallback must still create a validated, non-overwriting ZIP.
        with mock.patch("spicecore.freegpu.os.link", side_effect=OSError(1, "Operation not permitted")):
            manifest = self.export()
        self.assertEqual(freegpu.read_bundle(self.job, kind="job")["job_id"], manifest["job_id"])
        with self.assertRaises(FileExistsError):
            self.export()

    def test_same_explicit_job_id_inputs_and_options_have_deterministic_zip_bytes(self):
        self.export(job_id="deterministic-transcribe")
        original = self.job.read_bytes()
        os.utime(self.audio, (946684800, 946684800))
        second = self.root / "same-job.zip"
        freegpu.export_job(second, task="transcribe", inputs={"audio": self.audio},
                           job_id="deterministic-transcribe")
        self.assertEqual(original, second.read_bytes())

    def test_svd_image_job_has_bounded_t4_profile_and_roundtrips(self):
        image = self.root / "persona.png"
        image.write_bytes(b"explicit approved persona")
        manifest = self.export(task="video", inputs={"image": image, "prompt": "Scene descriptor"},
                               options={"pipeline": "svd-i2v"}, approved_fictional_persona=True)
        options = manifest["options"]
        self.assertEqual(options["model"], "stabilityai/stable-video-diffusion-img2vid-xt")
        self.assertEqual((options["width"], options["height"], options["frames"], options["steps"], options["fps"]),
                         (1024, 576, 25, 25, 7))
        self.assertEqual((options["motion_bucket_id"], options["noise_aug_strength"], options["decode_chunk_size"]),
                         (127, 0.02, 2))
        output = self.root / "video.mp4"
        output.write_bytes(b"only a transport fixture, not claimed inference")
        result = self.root / "result.zip"
        freegpu.write_result(self.job, result, artifacts={"video.mp4": output})
        imported = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "outputs")
        self.assertEqual(Path(imported["artifacts"]["video.mp4"]).read_bytes(), output.read_bytes())

    def test_svd_rejects_missing_image_unapproved_or_unbounded_motion_options(self):
        image = self.root / "persona.png"
        image.write_bytes(b"asset")
        for override in ({"frames": 17}, {"frames": True}, {"motion_bucket_id": 256},
                         {"noise_aug_strength": float("nan")}, {"decode_chunk_size": 25},
                         {"width": 1920}, {"guidance_scale": 6}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.export(task="video", inputs={"prompt": "Descriptor", "image": image},
                            options={"pipeline": "svd-i2v", **override}, approved_fictional_persona=True)
        with self.assertRaises(ValueError):
            self.export(task="video", inputs={"prompt": "Descriptor"}, options={"pipeline": "svd-i2v"})
        with self.assertRaisesRegex(ValueError, "approved"):
            self.export(task="video", inputs={"prompt": "Descriptor", "image": image}, options={"pipeline": "svd-i2v"})
        fourteen = freegpu.export_job(self.root / "14.zip", task="video", inputs={"prompt": "Descriptor", "image": image},
                                     options={"pipeline": "svd-i2v", "frames": 14}, approved_fictional_persona=True)
        self.assertEqual(fourteen["options"]["frames"], 14)

    def test_rejects_unlisted_or_altered_input_files(self):
        self.export()
        for mutate, extras in (
            (lambda name, data: data + b"tampered" if name.startswith("inputs/") else data, []),
            (None, [("inputs/unlisted.wav", b"secret")]),
        ):
            bad = self.rewrite(self.job, self.root / "bad.zip", mutate=mutate, extras=extras)
            with self.assertRaises(ValueError):
                freegpu.read_bundle(bad, kind="job")

    def test_rejects_altered_result_and_leaves_no_partial_import(self):
        result = self.result()
        bad = self.rewrite(result, self.root / "bad.zip",
                           mutate=lambda name, data: data + b"altered" if name.startswith("artifacts/") else data)
        destination = self.root / "imported"
        with self.assertRaisesRegex(ValueError, "hash|size"):
            freegpu.import_result(bad, job_bundle=self.job, output_dir=destination)
        self.assertFalse(destination.exists())

    def test_rejects_result_job_task_hash_version_and_paid_cost_mismatches(self):
        result = self.result()
        for key, value in (("job_id", "unrelated-job"), ("task", "tts"),
                           ("job_manifest_sha256", "0" * 64), ("version", 100), ("cost_cents", 1)):
            with self.subTest(key=key):
                def mutate(name, data):
                    if name == "manifest.json":
                        manifest = json.loads(data)
                        manifest[key] = value
                        return json.dumps(manifest).encode()
                    return data
                bad = self.rewrite(result, self.root / "bad.zip", mutate=mutate)
                with self.assertRaises(ValueError):
                    freegpu.import_result(bad, job_bundle=self.job, output_dir=self.root / "imported")

    def test_rejects_existing_or_symlinked_import_destination(self):
        result = self.result()
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "imported")
        existing = Path(outcome["artifact_paths"][0])
        existing.write_text("keep me")
        with self.assertRaises((ValueError, FileExistsError)):
            freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "imported")
        self.assertEqual(existing.read_text(), "keep me")
        link = self.root / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            freegpu.import_result(result, job_bundle=self.job, output_dir=link / "results")

    def test_result_writer_rejects_empty_or_wrong_task_artifact(self):
        self.export()
        empty = self.root / "empty.json"
        empty.touch()
        for artifacts in ({}, {"transcript.json": empty}, {"../transcript.json": self.audio}, {"video.mp4": self.audio}):
            with self.subTest(artifacts=list(artifacts)), self.assertRaises(ValueError):
                freegpu.write_result(self.job, self.root / "result.zip", artifacts=artifacts)

    def test_cli_export_and_import_emit_json(self):
        export = subprocess.run([sys.executable, "-m", "spicecore.freegpu", "export", "--task", "tts",
                                 "--text", "Hello", "--output", str(self.job)], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(export.returncode, 0, export.stderr)
        self.assertEqual(json.loads(export.stdout)["task"], "tts")
        result = self.root / "pending.zip"
        freegpu.write_result(self.job, result, status="pending", blocker="Piper voice weights missing")
        imported = subprocess.run([sys.executable, "-m", "spicecore.freegpu", "import", str(result),
                                   "--job", str(self.job), "--output-dir", str(self.root / "outputs")],
                                  cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(json.loads(imported.stdout)["status"], "pending")

    def test_worker_no_gpu_returns_valid_pending_bundle(self):
        self.export(task="video", inputs={"prompt": "A fictional adult walking in a park"})
        result = self.root / "pending.zip"
        environment = dict(os.environ, CUDA_VISIBLE_DEVICES="")
        worker = subprocess.run([sys.executable, str(ROOT / "scripts/freegpu-worker.py"),
                                 str(self.job), "--output", str(result)], cwd=ROOT, env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(worker.returncode, 0, worker.stderr)
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "outputs")
        self.assertEqual(outcome["status"], "pending")
        self.assertEqual(outcome["artifact_paths"], [])
        self.assertTrue(outcome["blocker"])

    def test_worker_piper_packages_only_a_real_validated_wav(self):
        self.export(task="tts", inputs={"text": "Hello world"})
        # A stand-in for the external Piper executable; the bridge and process
        # supervision are real. It refuses incorrect arguments instead of
        # swallowing them. Actual model inference requires installed weights.
        executable = self.root / "test-piper"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import sys, wave\n"
            "assert sys.stdin.read().strip() == 'Hello world'\n"
            "assert '--model' in sys.argv and '--output_file' in sys.argv\n"
            "path = sys.argv[sys.argv.index('--output_file') + 1]\n"
            "with wave.open(path, 'wb') as w:\n"
            " w.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))\n"
            " w.writeframes(b'\\x01\\x00' * 1600)\n", encoding="utf-8")
        executable.chmod(0o700)
        model = self.root / "voice.onnx"
        model.write_bytes(b"test weights")
        Path(str(model) + ".json").write_text("{}")
        result = self.root / "speech.zip"
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/freegpu-worker.py"), str(self.job),
                               "--output", str(result), "--piper-bin", str(executable),
                               "--piper-model", str(model)], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "outputs")
        self.assertEqual(outcome["status"], "completed")
        with wave.open(outcome["artifact_paths"][0]) as speech:
            self.assertEqual(speech.getnframes(), 1600)

    def test_worker_does_not_report_invalid_piper_output_as_completed(self):
        self.export(task="tts", inputs={"text": "Hello world"})
        executable = self.root / "broken-piper"
        executable.write_text(
            f"#!{sys.executable}\nimport sys\nfrom pathlib import Path\n"
            "Path(sys.argv[sys.argv.index('--output_file') + 1]).write_bytes(b'fake WAV')\n")
        executable.chmod(0o700)
        model = self.root / "voice.onnx"
        model.write_bytes(b"test weights")
        Path(str(model) + ".json").write_text("{}")
        result = self.root / "speech.zip"
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/freegpu-worker.py"), str(self.job),
                               "--output", str(result), "--piper-bin", str(executable),
                               "--piper-model", str(model)], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "outputs")
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["artifact_paths"], [])

    def test_worker_timeout_kills_the_batch_and_emits_pending(self):
        self.export(task="tts", inputs={"text": "Hello world"}, options={"timeout_seconds": 1})
        executable = self.root / "slow-piper"
        executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
        executable.chmod(0o700)
        model = self.root / "voice.onnx"
        model.write_bytes(b"test weights")
        Path(str(model) + ".json").write_text("{}")
        result = self.root / "timeout.zip"
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/freegpu-worker.py"), str(self.job),
                               "--output", str(result), "--piper-bin", str(executable),
                               "--piper-model", str(model)], cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outcome = freegpu.import_result(result, job_bundle=self.job, output_dir=self.root / "outputs")
        self.assertEqual(outcome["status"], "pending")
        self.assertIn("timeout", outcome["blocker"].lower())
        self.assertEqual(outcome["artifact_paths"], [])


if __name__ == "__main__":
    unittest.main()
