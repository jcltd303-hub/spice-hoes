"""Exercise the real worker adapter against a strict external-model stand-in.

Model weights/CUDA are unavailable in CI. Real FFmpeg validates the produced
media; the stand-in rejects wrong model arguments or unsupported text guidance.
"""

from contextlib import nullcontext
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg media validation requires installed binaries")
class FreeGPUWorkerTests(unittest.TestCase):
    def test_portrait_lipsync_input_is_bounded_without_rejecting_vertical_1080p(self):
        spec = importlib.util.spec_from_file_location('worker_portrait', ROOT / 'scripts/freegpu-worker.py')
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        with mock.patch.object(worker.subprocess, 'run') as run:
            run.return_value.stdout = '{"format":{"duration":"4.0"},"streams":[{"codec_type":"video","width":1080,"height":1920}]}'
            self.assertEqual(worker._probe('portrait.mp4', kind='video', max_seconds=60), 4.0)
            run.return_value.stdout = '{"format":{"duration":"4.0"},"streams":[{"codec_type":"video","width":1920,"height":1920}]}'
            with self.assertRaises(ValueError):
                worker._probe('oversized.mp4', kind='video', max_seconds=60)

    def test_svd_uses_fp16_offload_chunking_and_motion_without_prompt_on_t4(self):
        spec = importlib.util.spec_from_file_location("spice_freegpu_worker", ROOT / "scripts/freegpu-worker.py")
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "inputs").mkdir()
            outputs = root / "outputs"
            outputs.mkdir()
            image_path = root / "inputs/image.png"
            Image.new("RGB", (64, 64), "blue").save(image_path)
            options = {"pipeline": "svd-i2v", "model": "stabilityai/stable-video-diffusion-img2vid-xt",
                       "revision": "main", "width": 1024, "height": 576, "frames": 25,
                       "steps": 25, "fps": 7, "seed": 42, "motion_bucket_id": 127,
                       "noise_aug_strength": 0.02, "decode_chunk_size": 2}
            job = {"inputs": {"prompt": "Descriptor must not reach SVD", "image": "inputs/image.png"},
                   "options": options}
            test = self

            class Generator:
                def __init__(self, device):
                    test.assertEqual(device, "cpu")
                def manual_seed(self, seed):
                    test.assertEqual(seed, 42)
                    return self

            class StablePipeline:
                offloaded = False
                chunked = False
                def __init__(self):
                    self.unet = types.SimpleNamespace(enable_forward_chunking=self.chunk)
                @classmethod
                def from_pretrained(cls, model, **kwargs):
                    test.assertEqual(model, "stabilityai/stable-video-diffusion-img2vid-xt")
                    test.assertEqual(kwargs["torch_dtype"], "fp16")
                    test.assertEqual(kwargs["variant"], "fp16")
                    test.assertEqual(kwargs["revision"], "main")
                    test.assertTrue(kwargs["use_safetensors"])
                    return cls()
                def enable_model_cpu_offload(self):
                    self.offloaded = True
                def chunk(self):
                    self.chunked = True
                def __call__(self, image, **kwargs):
                    test.assertTrue(self.offloaded and self.chunked, "Low-memory optimizations must precede inference")
                    test.assertNotIn("prompt", kwargs)
                    test.assertEqual(image.size, (1024, 576))
                    for key, value in (("num_frames", 25), ("num_inference_steps", 25), ("fps", 7),
                                       ("decode_chunk_size", 2), ("motion_bucket_id", 127), ("noise_aug_strength", 0.02)):
                        test.assertEqual(kwargs[key], value)
                    return types.SimpleNamespace(frames=[[image] * 25])

            class RejectCogPipeline:
                @classmethod
                def from_pretrained(cls, *args, **kwargs):
                    raise AssertionError("SVD must not route through a CogVideoX pipeline")

            def export_to_video(frames, path, fps):
                raw = b"".join(frame.resize((128, 72)).tobytes() for frame in frames)
                subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", "128x72", "-r", str(fps), "-i", "pipe:0", "-an",
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", path], input=raw, check=True)

            diffusers = types.ModuleType("diffusers")
            diffusers.StableVideoDiffusionPipeline = StablePipeline
            diffusers.CogVideoXPipeline = RejectCogPipeline
            diffusers.CogVideoXImageToVideoPipeline = RejectCogPipeline
            utils = types.ModuleType("diffusers.utils")
            utils.load_image = lambda path: Image.open(path).convert("RGB")
            utils.export_to_video = export_to_video
            torch = types.SimpleNamespace(float16="fp16", bfloat16="bf16", Generator=Generator,
                                          inference_mode=nullcontext,
                                          cuda=types.SimpleNamespace(is_bf16_supported=lambda: False))
            with mock.patch.object(worker, "_gpu", return_value=torch), mock.patch.dict(
                "sys.modules", {"diffusers": diffusers, "diffusers.utils": utils}
            ):
                artifacts = worker._video(job, root, outputs, types.SimpleNamespace())
            self.assertEqual(set(artifacts), {"video.mp4"})
            self.assertGreater(artifacts["video.mp4"].stat().st_size, 100)
            self.assertAlmostEqual(worker._probe(artifacts["video.mp4"], kind="video", max_seconds=60), 25 / 7, places=1)


if __name__ == "__main__":
    unittest.main()
