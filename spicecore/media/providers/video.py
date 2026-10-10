"""Provider-agnostic video generation interfaces and implementations."""

from __future__ import annotations

import abc
import os
import shutil
import subprocess
import time
import uuid
from typing import Any, Dict, Optional


class VideoProvider(abc.ABC):
    """Abstract interface for short-form video generation providers."""

    @abc.abstractmethod
    def image_to_video(
        self,
        image_uri: str,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
        motion: str = "subtle push-in",
        seed: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Initiates an image-to-video generation job."""
        pass

    @abc.abstractmethod
    def text_image_to_video(
        self,
        prompt: str,
        image_uri: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generates video conditioned on both text prompt and initial image frame."""
        pass

    @abc.abstractmethod
    def talking_head(
        self,
        image_uri: str,
        audio_uri: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generates a talking-head video aligned with driving audio."""
        pass

    @abc.abstractmethod
    def status(self, job_id: str) -> Dict[str, Any]:
        """Polls the status of an in-flight video generation job."""
        pass

    @abc.abstractmethod
    def download(self, job_id: str, destination_path: str) -> str:
        """Retrieves and saves the rendered video output to destination_path."""
        pass


class MockVideoProvider(VideoProvider):
    """Provider for tests and offline development producing deterministic 9:16 MP4 assets."""

    def __init__(self, cost_cents_per_second: int = 2):
        self.cost_cents_per_second = cost_cents_per_second
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.ffmpeg_bin = shutil.which("ffmpeg")

    def _generate_video_file(self, output_path: str, duration: float, aspect_ratio: str = "9:16") -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

        if not self.ffmpeg_bin:
            self.ffmpeg_bin = shutil.which("ffmpeg")

        if self.ffmpeg_bin:
            # Generate color video stream with silent audio using ffmpeg lavfi
            cmd = [
                self.ffmpeg_bin, "-y",
                "-f", "lavfi", "-i", f"color=c=0x171320:s={width}x{height}:d={duration}:r=30",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration}",
                "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                output_path,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
            except Exception:
                pass

        # Fallback raw MP4 header
        ftyp = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
        mdat = b"\x00\x00\x00\x20mdat" + (b"\xaa" * 1024)
        with open(output_path, "wb") as f:
            f.write(ftyp)
            f.write(mdat)
        return output_path

    def image_to_video(
        self,
        image_uri: str,
        prompt: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
        motion: str = "subtle push-in",
        seed: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        job_id = f"mock-vid-{uuid.uuid4().hex[:12]}"
        cost_cents = int(duration_seconds * self.cost_cents_per_second)
        job_data = {
            "job_id": job_id,
            "status": "completed",
            "provider": "mock",
            "type": "image_to_video",
            "source_asset": image_uri,
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "motion": motion,
            "seed": seed or 42,
            "cost_cents": cost_cents,
            "output_uri": f"/tmp/mock_videos/{job_id}.mp4",
            "created_at": time.time(),
        }
        self.jobs[job_id] = job_data
        return job_data

    def text_image_to_video(
        self,
        prompt: str,
        image_uri: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "9:16",
        **kwargs,
    ) -> Dict[str, Any]:
        return self.image_to_video(
            image_uri=image_uri,
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            **kwargs,
        )

    def talking_head(
        self,
        image_uri: str,
        audio_uri: str,
        **kwargs,
    ) -> Dict[str, Any]:
        job_id = f"mock-talk-{uuid.uuid4().hex[:12]}"
        cost_cents = 15
        job_data = {
            "job_id": job_id,
            "status": "completed",
            "provider": "mock",
            "type": "talking_head",
            "source_asset": image_uri,
            "audio_uri": audio_uri,
            "duration_seconds": 6.0,
            "cost_cents": cost_cents,
            "output_uri": f"/tmp/mock_videos/{job_id}.mp4",
            "created_at": time.time(),
        }
        self.jobs[job_id] = job_data
        return job_data

    def status(self, job_id: str) -> Dict[str, Any]:
        if job_id not in self.jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        return self.jobs[job_id]

    def download(self, job_id: str, destination_path: str) -> str:
        job = self.status(job_id)
        duration = float(job.get("duration_seconds", 5.0))
        aspect_ratio = job.get("aspect_ratio", "9:16")
        self._generate_video_file(destination_path, duration=duration, aspect_ratio=aspect_ratio)
        return destination_path


class LumaVideoProvider(VideoProvider):
    """Reserved real Luma adapter. Fails closed until real API I/O is implemented."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("LUMA_API_KEY", "")

    def _unavailable(self):
        if not self.api_key:
            raise RuntimeError("LUMA_API_KEY is not configured")
        raise RuntimeError("Luma video adapter is not production-wired yet")

    def image_to_video(self, image_uri: str, prompt: str, duration_seconds: float = 5.0,
                       aspect_ratio: str = "9:16", motion: str = "subtle push-in",
                       seed: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        self._unavailable()

    def text_image_to_video(self, prompt: str, image_uri: str, duration_seconds: float = 5.0,
                            aspect_ratio: str = "9:16", **kwargs) -> Dict[str, Any]:
        self._unavailable()

    def talking_head(self, image_uri: str, audio_uri: str, **kwargs) -> Dict[str, Any]:
        self._unavailable()

    def status(self, job_id: str) -> Dict[str, Any]:
        self._unavailable()

    def download(self, job_id: str, destination_path: str) -> str:
        self._unavailable()


def video_provider_from_env() -> VideoProvider:
    """Build the configured video provider without coupling the media pipeline to a model vendor."""
    provider = os.getenv("SPICE_VIDEO_PROVIDER", "freegpu").strip().lower()
    if provider in ("", "mock"):
        return MockVideoProvider()
    if provider == "comfyui":
        from .comfyui import ComfyUIVideoProvider
        return ComfyUIVideoProvider()
    if provider == "freegpu":
        from .freegpu import FreeGPUVideoProvider
        return FreeGPUVideoProvider()
    if provider == "luma":
        return LumaVideoProvider()
    raise RuntimeError(f"Unknown SPICE_VIDEO_PROVIDER: {provider}")
