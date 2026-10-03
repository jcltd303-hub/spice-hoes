import os
import unittest
from unittest import mock

from spicecore.media.providers.voice import PiperVoiceProvider, voice_provider_from_env
from spicecore.media.providers.lipsync import (
    MuseTalkLipSyncProvider,
    Wav2LipLocalProvider,
    lipsync_provider_from_env,
)


class LocalMediaProviderTests(unittest.TestCase):
    def test_voice_factory_selects_piper(self):
        with mock.patch.dict(
            os.environ,
            {"SPICE_VOICE_PROVIDER": "piper", "PIPER_MODEL": "/tmp/voice.onnx"},
            clear=False,
        ):
            self.assertIsInstance(voice_provider_from_env(), PiperVoiceProvider)

    def test_lipsync_factory_selects_musetalk(self):
        with mock.patch.dict(
            os.environ,
            {"SPICE_LIPSYNC_PROVIDER": "musetalk", "MUSETALK_DIR": "/tmp/musetalk"},
            clear=False,
        ):
            self.assertIsInstance(lipsync_provider_from_env(), MuseTalkLipSyncProvider)

    def test_wav2lip_fails_closed_without_noncommercial_override(self):
        with mock.patch.dict(os.environ, {"ALLOW_NONCOMMERCIAL_WAV2LIP": "false"}, clear=False):
            with self.assertRaises(RuntimeError):
                Wav2LipLocalProvider(root="/tmp").sync("/tmp/no.mp4", "/tmp/no.wav")


if __name__ == "__main__":
    unittest.main()
