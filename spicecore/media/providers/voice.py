"""Voice identity models and synthesis providers."""

from __future__ import annotations

import abc
import math
import os
import struct
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VoiceProfile:
    persona_id: str
    voice_profile_id: str
    version: str = "1.0.0"
    provider: str = "mock"
    voice_id: str = "default"
    language: str = "en-US"
    accent: str = "general"
    tone: str = "warm"
    pitch: float = 1.0
    pace: float = 1.0
    style: str = "conversational"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceProfile":
        return cls(**data)


# Persistent Canonical Voice Profiles for the 5 Adult Archetypes
CANONICAL_VOICE_PROFILES: Dict[str, VoiceProfile] = {
    "zara_voss": VoiceProfile(
        persona_id="zara_voss",
        voice_profile_id="vp_zara_v1",
        version="1.0.0",
        provider="android-offline",
        voice_id="default",  # Select an installed offline voice with SPICE_ANDROID_VOICE_MAP.
        language="en-GB",
        accent="London urban",
        tone="direct, kinetic, confident",
        pitch=0.98,
        pace=1.10,
        style="energetic rhythmic narrative",
    ),
    "tess_wilder": VoiceProfile(
        persona_id="tess_wilder",
        voice_profile_id="vp_tess_v1",
        version="1.0.0",
        provider="android-offline",
        voice_id="default",  # Select an installed offline voice with SPICE_ANDROID_VOICE_MAP.
        language="en-US",
        accent="Pacific Northwest",
        tone="competitive, encouraging, quick-witted",
        pitch=1.02,
        pace=1.05,
        style="practical athletic coaching",
    ),
    "lila_hart": VoiceProfile(
        persona_id="lila_hart",
        voice_profile_id="vp_lila_v1",
        version="1.0.0",
        provider="android-offline",
        voice_id="default",  # Select an installed offline voice with SPICE_ANDROID_VOICE_MAP.
        language="en-US",
        accent="Northern California warm",
        tone="warm, witty, playful, unmistakably adult",
        pitch=1.05,
        pace=0.98,
        style="intimate studio conversation",
    ),
    "ruby_wren": VoiceProfile(
        persona_id="ruby_wren",
        voice_profile_id="vp_ruby_v1",
        version="1.0.0",
        provider="android-offline",
        voice_id="default",  # Select an installed offline voice with SPICE_ANDROID_VOICE_MAP.
        language="en-GB",
        accent="Northern English articulate",
        tone="fiery, eloquent, irreverent",
        pitch=1.01,
        pace=1.12,
        style="provocative cultural commentary",
    ),
    "celeste_vale": VoiceProfile(
        persona_id="celeste_vale",
        voice_profile_id="vp_celeste_v1",
        version="1.0.0",
        provider="android-offline",
        voice_id="default",  # Select an installed offline voice with SPICE_ANDROID_VOICE_MAP.
        language="en-US",
        accent="Mid-Atlantic polished",
        tone="precise, dryly funny, selective",
        pitch=0.92,
        pace=0.95,
        style="curated aesthetic critique",
    ),
}


class VoiceProvider(abc.ABC):
    """Abstract interface for speech synthesis and voice transformations."""

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        voice_profile: VoiceProfile,
        output_path: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Synthesizes text using specified voice profile into an audio file."""
        pass

    @abc.abstractmethod
    def transform(
        self,
        audio_path: str,
        transformation_spec: Dict[str, Any],
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Applies pitch/tempo/reverb or equalization transforms to an audio track."""
        pass


class MockVoiceProvider(VoiceProvider):
    """Mock voice provider generating valid PCM WAV files with synthetic tone."""

    def __init__(self, cost_cents_per_second: float = 0.5):
        self.cost_cents_per_second = cost_cents_per_second

    def synthesize(
        self,
        text: str,
        voice_profile: VoiceProfile,
        output_path: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not output_path:
            out_dir = "/tmp/mock_audio"
            os.makedirs(out_dir, exist_ok=True)
            output_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:10]}.wav")

        words = len(text.split())
        # Estimate duration based on pace: ~140 wpm * pace
        wpm = 140.0 * (voice_profile.pace or 1.0)
        duration_seconds = max(2.0, round((words / wpm) * 60.0, 2))
        cost_cents = max(2, int(duration_seconds * self.cost_cents_per_second))

        self._generate_wav(output_path, duration_seconds=duration_seconds, freq=220.0 * voice_profile.pitch)

        return {
            "audio_path": output_path,
            "duration_seconds": duration_seconds,
            "cost_cents": cost_cents,
            "provider": "mock",
            "voice_profile_id": voice_profile.voice_profile_id,
            "persona_id": voice_profile.persona_id,
            "word_count": words,
        }

    def _generate_wav(self, file_path: str, duration_seconds: float, freq: float = 440.0) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        sample_rate = 44100
        num_samples = int(sample_rate * duration_seconds)

        with wave.open(file_path, "w") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)

            # Generate gentle sine wave with soft fade-in/fade-out
            frames = bytearray()
            for i in range(num_samples):
                t = float(i) / sample_rate
                # Envelope
                envelope = 1.0
                fade_samples = int(sample_rate * 0.05)
                if i < fade_samples:
                    envelope = i / fade_samples
                elif i > num_samples - fade_samples:
                    envelope = (num_samples - i) / fade_samples

                sample_val = int(envelope * 12000.0 * math.sin(2.0 * math.pi * freq * t))
                frames.extend(struct.pack("<h", sample_val))
            wav_file.writeframes(frames)

    def transform(
        self,
        audio_path: str,
        transformation_spec: Dict[str, Any],
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        out_path = output_path or audio_path
        return {"output_path": out_path, "applied": transformation_spec}


class ElevenLabsVoiceProvider(VoiceProvider):
    """Reserved real ElevenLabs adapter. Fails closed until real API I/O is implemented."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")

    def _unavailable(self):
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured")
        raise RuntimeError("ElevenLabs voice adapter is not production-wired yet")

    def synthesize(self, text: str, voice_profile: VoiceProfile,
                   output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        self._unavailable()

    def transform(self, audio_path: str, transformation_spec: Dict[str, Any],
                  output_path: Optional[str] = None) -> Dict[str, Any]:
        self._unavailable()


class PiperVoiceProvider(VoiceProvider):
    """Local Piper TTS subprocess adapter.

    Piper is kept behind a process boundary. The maintained upstream is GPLv3;
    this project does not vendor or modify Piper source.
    """

    def __init__(self, binary: Optional[str] = None, model: Optional[str] = None,
                 config: Optional[str] = None, voice_map_json: Optional[str] = None):
        self.binary = binary or os.getenv("PIPER_BIN", "piper")
        self.model = model or os.getenv("PIPER_MODEL", "")
        self.config = config or os.getenv("PIPER_CONFIG", "")
        raw = voice_map_json or os.getenv("PIPER_VOICE_MAP", "{}")
        try:
            import json as _json
            self.voice_map = _json.loads(raw) if raw else {}
        except Exception as exc:
            raise RuntimeError("PIPER_VOICE_MAP must be valid JSON") from exc

    def _model_for(self, voice_profile: VoiceProfile) -> str:
        return str(
            self.voice_map.get(voice_profile.persona_id)
            or self.voice_map.get(voice_profile.voice_profile_id)
            or self.model
        ).strip()

    def synthesize(self, text: str, voice_profile: VoiceProfile,
                   output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        import shutil as _shutil
        import subprocess as _subprocess
        if not _shutil.which(self.binary) and not os.path.isfile(self.binary):
            raise RuntimeError(f"Piper executable not found: {self.binary}")
        model = self._model_for(voice_profile)
        if not model or not os.path.isfile(model):
            raise RuntimeError("Set PIPER_MODEL or PIPER_VOICE_MAP to a Piper ONNX voice.")
        if output_path is None:
            out_dir = "/tmp/spice_piper"
            os.makedirs(out_dir, exist_ok=True)
            output_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:10]}.wav")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cmd = [self.binary, "--model", model, "--output-file", output_path]
        if self.config and os.path.isfile(self.config):
            cmd += ["--config", self.config]
        pace = max(0.25, float(voice_profile.pace or 1.0))
        cmd += ["--length-scale", str(1.0 / pace)]
        proc = _subprocess.run(
            cmd, input=text + "\n", text=True, capture_output=True,
            timeout=int(os.getenv("PIPER_TIMEOUT_SECONDS", "180"))
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Piper failed: {(proc.stderr or proc.stdout).strip()[-2000:]}")
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Piper completed without producing audio")
        with wave.open(output_path, "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())
        return {
            "audio_path": output_path,
            "duration_seconds": round(duration, 3),
            "cost_cents": 0,
            "provider": "piper-local",
            "voice_profile_id": voice_profile.voice_profile_id,
            "persona_id": voice_profile.persona_id,
            "model": os.path.basename(model),
        }

    def transform(self, audio_path: str, transformation_spec: Dict[str, Any],
                  output_path: Optional[str] = None) -> Dict[str, Any]:
        if output_path and output_path != audio_path:
            import shutil as _shutil
            _shutil.copyfile(audio_path, output_path)
            return {"output_path": output_path, "applied": {}}
        return {"output_path": audio_path, "applied": {}}


class AndroidVoiceProvider(VoiceProvider):
    """Use Android offline voices without pip/native wheels in Termux."""

    def synthesize(self, text, voice_profile, output_path=None, **kwargs):
        from ...android_voice import AndroidVoiceClient, voice_fields
        if output_path is None:
            output_path = str(Path(os.getenv('TMPDIR', '/tmp')) / f'spice_voice_{uuid.uuid4().hex}.wav')
        result = AndroidVoiceClient().synthesize(text, output_path, **voice_fields(voice_profile))
        return {**result, 'voice_profile_id': voice_profile.voice_profile_id,
                'persona_id': voice_profile.persona_id}

    def transform(self, audio_path, transformation_spec, output_path=None):
        if transformation_spec:
            raise RuntimeError('Apply voice transforms with FFmpeg; Android synthesis uses profile pitch/pace')
        if output_path and output_path != audio_path:
            import shutil
            shutil.copyfile(audio_path, output_path)
        return {'output_path': output_path or audio_path, 'applied': {}}


def voice_provider_from_env() -> VoiceProvider:
    provider = os.getenv("SPICE_VOICE_PROVIDER", "android").strip().lower()
    if provider in ("", "mock"):
        return MockVoiceProvider()
    if provider == "piper":
        return PiperVoiceProvider()
    if provider in ("android", "android-offline"):
        return AndroidVoiceProvider()
    if provider == "elevenlabs":
        return ElevenLabsVoiceProvider()
    raise RuntimeError(f"Unknown SPICE_VOICE_PROVIDER: {provider}")
