"""Lip-sync provider abstraction separating facial animation from voice and base video."""

from __future__ import annotations

import abc
import os
import shutil
import time
import uuid
from typing import Any, Dict, Optional


class LipSyncProvider(abc.ABC):
    """Abstract interface for driving facial movement and mouth shapes from driving audio."""

    @abc.abstractmethod
    def sync(
        self,
        video_uri: str,
        audio_uri: str,
        output_path: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Aligns mouth movement in video_uri to match phonemes in audio_uri."""
        pass

    @abc.abstractmethod
    def status(self, job_id: str) -> Dict[str, Any]:
        """Checks status of asynchronous lip-sync job."""
        pass


class MockLipSyncProvider(LipSyncProvider):
    """Mock lip-sync provider that validates inputs and produces synchronized output."""

    def __init__(self, cost_cents: int = 15):
        self.cost_cents = cost_cents
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def sync(
        self,
        video_uri: str,
        audio_uri: str,
        output_path: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        job_id = f"lipsync-{uuid.uuid4().hex[:10]}"
        if not output_path:
            out_dir = "/tmp/mock_lipsync"
            os.makedirs(out_dir, exist_ok=True)
            output_path = os.path.join(out_dir, f"{job_id}.mp4")

        # Copy or link source video to output if local file
        if os.path.exists(video_uri):
            shutil.copyfile(video_uri, output_path)
        else:
            # Write stub
            with open(output_path, "wb") as f:
                f.write(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")

        result = {
            "job_id": job_id,
            "status": "completed",
            "provider": "mock_lipsync",
            "synced_video_path": output_path,
            "source_video": video_uri,
            "source_audio": audio_uri,
            "cost_cents": self.cost_cents,
            "timestamp": time.time(),
        }
        self.jobs[job_id] = result
        return result

    def status(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        return self.jobs[job_id]


class SyncLabsLipSyncProvider(LipSyncProvider):
    """Reserved real SyncLabs adapter. Fails closed until real API I/O is implemented."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SYNCLABS_API_KEY", "")

    def _unavailable(self):
        if not self.api_key:
            raise RuntimeError("SYNCLABS_API_KEY is not configured")
        raise RuntimeError("SyncLabs lip-sync adapter is not production-wired yet")

    def sync(self, video_uri: str, audio_uri: str,
             output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        self._unavailable()

    def status(self, job_id: str) -> Dict[str, Any]:
        self._unavailable()


def _yaml_quote(value: str) -> str:
    import json
    return json.dumps(os.path.abspath(value))


class MuseTalkLipSyncProvider(LipSyncProvider):
    """Local MuseTalk 1.5 subprocess adapter."""

    def __init__(self, root: Optional[str] = None, python_bin: Optional[str] = None):
        self.root = os.path.abspath(root or os.getenv("MUSETALK_DIR", "vendor/MuseTalk"))
        self.python_bin = python_bin or os.getenv("MUSETALK_PYTHON", "python3")
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def sync(self, video_uri: str, audio_uri: str,
             output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        import subprocess
        import tempfile
        if not os.path.isdir(self.root):
            raise RuntimeError(f"MuseTalk directory not found: {self.root}")
        if not os.path.isfile(video_uri):
            raise FileNotFoundError(video_uri)
        if not os.path.isfile(audio_uri):
            raise FileNotFoundError(audio_uri)
        job_id = f"musetalk-{uuid.uuid4().hex[:10]}"
        output_path = output_path or os.path.join("/tmp", "spice_musetalk", f"{job_id}.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        result_dir = os.path.join("/tmp", "spice_musetalk", job_id)
        os.makedirs(result_dir, exist_ok=True)
        result_name = os.path.basename(output_path)
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as cfg:
            cfg.write("task_0:\n")
            cfg.write(f"  video_path: {_yaml_quote(video_uri)}\n")
            cfg.write(f"  audio_path: {_yaml_quote(audio_uri)}\n")
            cfg.write(f"  result_name: {_yaml_quote(result_name)}\n")
            config_path = cfg.name
        model_dir = os.getenv("MUSETALK_MODEL_DIR", os.path.join(self.root, "models", "musetalkV15"))
        cmd = [
            self.python_bin, "-m", "scripts.inference",
            "--inference_config", config_path,
            "--result_dir", result_dir,
            "--unet_model_path", os.path.join(model_dir, "unet.pth"),
            "--unet_config", os.path.join(model_dir, "musetalk.json"),
            "--version", "v15",
            "--fps", str(int(kwargs.get("fps", 25))),
        ]
        ffmpeg_path = os.getenv("MUSETALK_FFMPEG_PATH", "").strip()
        if ffmpeg_path:
            cmd += ["--ffmpeg_path", ffmpeg_path]
        try:
            proc = subprocess.run(
                cmd, cwd=self.root, capture_output=True, text=True,
                timeout=int(os.getenv("MUSETALK_TIMEOUT_SECONDS", "1800"))
            )
        finally:
            try:
                os.unlink(config_path)
            except OSError:
                pass
        if proc.returncode != 0:
            raise RuntimeError(f"MuseTalk failed: {(proc.stderr or proc.stdout).strip()[-4000:]}")
        generated = os.path.join(result_dir, "v15", result_name)
        if not os.path.isfile(generated):
            raise RuntimeError(f"MuseTalk did not create expected output: {generated}")
        shutil.copyfile(generated, output_path)
        result = {
            "job_id": job_id, "status": "completed", "provider": "musetalk-local-v1.5",
            "synced_video_path": output_path, "source_video": video_uri,
            "source_audio": audio_uri, "cost_cents": 0, "timestamp": time.time(),
        }
        self.jobs[job_id] = result
        return result

    def status(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        return self.jobs[job_id]


class Wav2LipLocalProvider(LipSyncProvider):
    """Research/dev-only Wav2Lip adapter; public upstream is non-commercial."""

    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root or os.getenv("WAV2LIP_DIR", "vendor/Wav2Lip"))
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def sync(self, video_uri: str, audio_uri: str,
             output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        import subprocess
        if os.getenv("ALLOW_NONCOMMERCIAL_WAV2LIP", "").lower() not in ("1", "true", "yes"):
            raise RuntimeError(
                "Wav2Lip public upstream is non-commercial. Use MuseTalk for production; "
                "enable ALLOW_NONCOMMERCIAL_WAV2LIP only for research/dev."
            )
        checkpoint = os.getenv("WAV2LIP_CHECKPOINT", "")
        if not checkpoint:
            raise RuntimeError("WAV2LIP_CHECKPOINT is required")
        output_path = output_path or os.path.join("/tmp", f"wav2lip-{uuid.uuid4().hex[:10]}.mp4")
        cmd = [os.getenv("WAV2LIP_PYTHON", "python3"), "inference.py",
               "--checkpoint_path", checkpoint, "--face", video_uri,
               "--audio", audio_uri, "--outfile", output_path]
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True,
                              timeout=int(os.getenv("WAV2LIP_TIMEOUT_SECONDS", "1800")))
        if proc.returncode != 0:
            raise RuntimeError(f"Wav2Lip failed: {(proc.stderr or proc.stdout).strip()[-4000:]}")
        job_id = f"wav2lip-{uuid.uuid4().hex[:10]}"
        result = {"job_id": job_id, "status": "completed",
                  "provider": "wav2lip-local-noncommercial",
                  "synced_video_path": output_path, "cost_cents": 0, "timestamp": time.time()}
        self.jobs[job_id] = result
        return result

    def status(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        return self.jobs[job_id]


def lipsync_provider_from_env() -> LipSyncProvider:
    provider = os.getenv("SPICE_LIPSYNC_PROVIDER", "mock").strip().lower()
    if provider in ("", "mock"):
        return MockLipSyncProvider(cost_cents=0)
    if provider == "musetalk":
        return MuseTalkLipSyncProvider()
    if provider == "wav2lip":
        return Wav2LipLocalProvider()
    if provider == "synclabs":
        return SyncLabsLipSyncProvider()
    raise RuntimeError(f"Unknown SPICE_LIPSYNC_PROVIDER: {provider}")
