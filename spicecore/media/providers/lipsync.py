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
