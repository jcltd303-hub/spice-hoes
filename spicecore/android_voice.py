"""Offline Android speech over the companion's loopback API."""

from __future__ import annotations

import base64
import io
import json
import os
import wave
from pathlib import Path

from .local_compute import _get_json, loopback_url
from .providers import _post_json


class AndroidVoiceClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = loopback_url(base_url or os.getenv('SPICE_ANDROID_VOICE_URL', 'http://127.0.0.1:8082'))
        self.token = token if token is not None else os.getenv('SPICE_ANDROID_VOICE_TOKEN', '')

    def _headers(self):
        if not self.token:
            raise RuntimeError('Pair voice in the Android companion: tap Copy voice pairing command and set SPICE_ANDROID_VOICE_TOKEN')
        if len(self.token) > 256 or not self.token.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in self.token):
            raise ValueError('Invalid Android voice pairing token')
        return {'Authorization': 'Bearer ' + self.token}

    def health(self):
        return _get_json(self.base_url + '/voice/health')

    @staticmethod
    def _fields(text, **kwargs):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('Speech text must contain 1..4000 characters')
        return {'text': text, **{k: v for k, v in kwargs.items()
                                if k in ('voice_id', 'language', 'pitch', 'pace') and v is not None}}

    def synthesize(self, text, output_path, **kwargs):
        result = _post_json(self.base_url + '/voice/synthesize', self._fields(text, **kwargs), self._headers(), timeout=90)
        try:
            encoded = result['audio_base64']
            if not isinstance(encoded, str) or len(encoded) > 24 * 1024 * 1024:
                raise ValueError
            raw = base64.b64decode(encoded, validate=True)
            with wave.open(io.BytesIO(raw), 'rb') as audio:
                if audio.getnframes() <= 0 or audio.getframerate() <= 0 or audio.getsampwidth() != 2:
                    raise ValueError
                duration = audio.getnframes() / audio.getframerate()
                expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
                if len(audio.readframes(audio.getnframes())) != expected:
                    raise ValueError
        except (KeyError, TypeError, ValueError, wave.Error, EOFError):
            raise RuntimeError('Android companion returned invalid PCM WAV audio') from None
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {'audio_path': str(path), 'duration_seconds': round(duration, 3),
                'provider': 'android-offline', 'cost_cents': 0}

    def speak(self, text, **kwargs):
        return _post_json(self.base_url + '/voice/speak', self._fields(text, **kwargs), self._headers(), timeout=90)

    def listen(self, language='en-US', timeout_seconds=20):
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
            raise ValueError('Microphone timeout must be 1..30 seconds')
        health = self.health()
        if not health.get('recognition_available'):
            raise RuntimeError('Android on-device recognition unavailable; open companion and grant microphone access')
        result = _post_json(self.base_url + '/voice/listen',
                            {'language': language, 'timeout_seconds': timeout_seconds}, self._headers(),
                            timeout=timeout_seconds + 10)
        if not isinstance(result.get('text'), str) or not result['text'].strip():
            raise RuntimeError('On-device recognition returned no speech')
        return result


def voice_fields(profile):
    try:
        mapping = json.loads(os.getenv('SPICE_ANDROID_VOICE_MAP', '{}'))
        if not isinstance(mapping, dict):
            raise ValueError
        voice = mapping.get(profile.persona_id) or mapping.get(profile.voice_profile_id)
        if voice is not None and not isinstance(voice, str):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('SPICE_ANDROID_VOICE_MAP must map persona/profile IDs to offline voice names') from None
    return {'voice_id': voice, 'language': profile.language, 'pitch': profile.pitch, 'pace': profile.pace}


def voice_turn(voice, provider, persona, *, history=None, language='en-US', timeout_seconds=20):
    """One explicit microphone -> local model -> offline speaker turn."""
    heard = voice.listen(language=language, timeout_seconds=timeout_seconds)['text']
    context = (history or [])[-8:]
    system = (f"You are {persona.get('name', persona.get('id', 'the assistant'))}, a disclosed fictional AI adult character. "
              'Reply in one or two short spoken sentences. Do not invent project facts or claim actions were performed. ' +
              json.dumps(persona, ensure_ascii=False))
    prompt = '\n'.join([*context, 'User: ' + heard])
    answer = provider.chat(system, prompt, max_tokens=256)
    from .media.providers.voice import CANONICAL_VOICE_PROFILES, VoiceProfile
    profile = CANONICAL_VOICE_PROFILES.get(persona.get('id'), VoiceProfile(persona.get('id', 'assistant'), 'default'))
    spoken = voice.speak(answer, **{**voice_fields(profile), 'language': language})
    if history is not None:
        history.extend(['User: ' + heard, 'Assistant: ' + answer])
        del history[:-8]
    return {'heard': heard, 'answer': answer, 'voice_provider': spoken.get('provider', 'android-offline'),
            'model_provider': getattr(provider, 'model_name', 'local'),
            'cost_cents': 0 if getattr(provider, 'local_compute', False) else None}
