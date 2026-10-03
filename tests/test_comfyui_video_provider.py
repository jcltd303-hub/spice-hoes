import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spicecore.media.providers.comfyui import ComfyUIVideoProvider
from spicecore.media.providers.video import MockVideoProvider, video_provider_from_env


class ComfyUIProviderTests(unittest.TestCase):
    def _provider(self, workflow_path="/tmp/workflow.json"):
        return ComfyUIVideoProvider(
            base_url="http://127.0.0.1:8188",
            workflow_path=workflow_path,
            timeout_seconds=5,
            poll_seconds=0.01,
        )

    def test_injects_common_wan_ltx_inputs_and_placeholders(self):
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "__SPICE_IMAGE__"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "__SPICE_PROMPT__"}},
            "3": {"class_type": "Sampler", "inputs": {
                "noise_seed": 1, "width": 1, "height": 1, "num_frames": 1, "fps": 1
            }},
        }
        out = self._provider()._inject(
            workflow, prompt="portrait walking", image="source.png", seed=123,
            width=576, height=1024, frames=121, fps=24,
        )
        self.assertEqual(out["1"]["inputs"]["image"], "source.png")
        self.assertEqual(out["2"]["inputs"]["text"], "portrait walking")
        self.assertEqual(out["3"]["inputs"]["noise_seed"], 123)
        self.assertEqual(out["3"]["inputs"]["width"], 576)
        self.assertEqual(out["3"]["inputs"]["height"], 1024)
        self.assertEqual(out["3"]["inputs"]["num_frames"], 121)
        self.assertEqual(out["3"]["inputs"]["fps"], 24)

    def test_provider_factory_defaults_to_mock(self):
        with mock.patch.dict(os.environ, {"SPICE_VIDEO_PROVIDER": "mock"}, clear=False):
            self.assertIsInstance(video_provider_from_env(), MockVideoProvider)

    def test_provider_factory_builds_comfyui(self):
        with tempfile.TemporaryDirectory() as td:
            wf = Path(td) / "wf.json"
            wf.write_text("{}", encoding="utf-8")
            env = {
                "SPICE_VIDEO_PROVIDER": "comfyui",
                "COMFYUI_BASE_URL": "http://example.invalid",
                "COMFYUI_WORKFLOW": str(wf),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertIsInstance(video_provider_from_env(), ComfyUIVideoProvider)


if __name__ == "__main__":
    unittest.main()
