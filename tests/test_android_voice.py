import base64
import io
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from spicecore.android_voice import AndroidVoiceClient, voice_turn
from spicecore.media.providers.voice import VoiceProfile, voice_provider_from_env


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 1600)
    return out.getvalue()


class AndroidVoiceTests(unittest.TestCase):
    def test_media_voice_selection_writes_real_wav_and_reports_zero_service_cost(self):
        payload = wav_bytes()
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            'SPICE_VOICE_PROVIDER': 'android',
            'SPICE_ANDROID_VOICE_TOKEN': 'test-pairing-token',
            'SPICE_ANDROID_VOICE_MAP': json.dumps({'zara': 'offline-en'})}, clear=True), \
                patch('spicecore.android_voice._post_json') as post:
            post.return_value = {'audio_base64': base64.b64encode(payload).decode(),
                                 'mime_type': 'audio/wav', 'provider': 'android-offline'}
            path = Path(root) / 'speech.wav'
            result = voice_provider_from_env().synthesize('Hello', VoiceProfile('zara', 'vp'), str(path))
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(result['cost_cents'], 0)
            self.assertEqual(result['provider'], 'android-offline')
            self.assertAlmostEqual(result['duration_seconds'], .1)
            self.assertEqual(post.call_args.args[1]['voice_id'], 'offline-en')
            self.assertEqual(post.call_args.args[2], {'Authorization': 'Bearer test-pairing-token'})

    def test_invalid_synthesis_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as root, \
                patch('spicecore.android_voice._post_json', return_value={'audio_base64': 'bm90LXdhdg=='}):
            path = Path(root) / 'voice.wav'
            with self.assertRaises(RuntimeError):
                AndroidVoiceClient(token='test-pairing-token').synthesize('test', path)
            self.assertFalse(path.exists())

    def test_listen_requires_actual_on_device_recognition(self):
        with patch('spicecore.android_voice._get_json', return_value={'tts_ready': True, 'recognition_available': False}):
            with self.assertRaisesRegex(RuntimeError, 'on-device'):
                AndroidVoiceClient().listen()

    def test_loopback_only_and_bounded_microphone_session(self):
        with self.assertRaises(ValueError):
            AndroidVoiceClient('https://example.com')
        with self.assertRaises(ValueError):
            AndroidVoiceClient().listen(timeout_seconds=120)

    def test_voice_actions_require_explicit_pairing(self):
        with patch('spicecore.android_voice._post_json') as post:
            with self.assertRaisesRegex(RuntimeError, 'Pair voice'):
                AndroidVoiceClient(token='').speak('hello')
            post.assert_not_called()

    def test_conversation_connects_recognition_model_and_offline_playback(self):
        class Voice:
            def __init__(self): self.spoken = []
            def listen(self, **kwargs): return {'text': 'What is planned today?'}
            def speak(self, text, **kwargs): self.spoken.append(text); return {'provider': 'android-offline'}
        class Model:
            def chat(self, system, user, **kwargs):
                self.prompt = user
                return 'We can draft the next post.'
        voice, model = Voice(), Model()
        result = voice_turn(voice, model, {'id': 'zara', 'name': 'Zara'}, history=[])
        self.assertEqual(result['heard'], 'What is planned today?')
        self.assertEqual(voice.spoken, ['We can draft the next post.'])
        self.assertIn('What is planned today?', model.prompt)
