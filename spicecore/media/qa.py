"""Automated technical QA for rendered video assets before human review."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .models import QAReport


class VideoQA:
    """Automated technical validation gate for rendered video files."""

    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
        target_aspect_ratio: str = "9:16",
        min_duration_seconds: float = 3.0,
        max_duration_seconds: float = 65.0,
        min_fps: float = 24.0,
        max_fps: float = 60.0,
        allowed_video_codecs: Optional[list] = None,
        allowed_audio_codecs: Optional[list] = None,
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.target_aspect_ratio = target_aspect_ratio
        self.min_duration_seconds = min_duration_seconds
        self.max_duration_seconds = max_duration_seconds
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.allowed_video_codecs = allowed_video_codecs or ["h264", "hevc", "avc1", "mp4v"]
        self.allowed_audio_codecs = allowed_audio_codecs or ["aac", "mp3", "opus"]

    def run_ffprobe(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extracts streams and format metadata via ffprobe if installed."""
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            return None

        cmd = [
            ffprobe_bin,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception:
            pass
        return None

    def evaluate(self, video_path: str, simulated_meta: Optional[Dict[str, Any]] = None) -> QAReport:
        """Evaluates video file integrity, format, dimensions, audio, and frames."""
        checks: Dict[str, bool] = {
            "file_integrity": False,
            "resolution": False,
            "aspect_ratio": False,
            "duration": False,
            "fps": False,
            "codec": False,
            "audio_present": False,
            "no_corrupt_frames": False,
        }
        details: Dict[str, Any] = {"unmeasured": ["black_frames", "audio_clipping"]}

        path = Path(video_path)
        if not path.exists() or path.stat().st_size == 0:
            return QAReport(
                passed=False,
                score=0.0,
                checks=checks,
                details={"error": "File does not exist or is empty"},
            )

        file_size = path.stat().st_size
        details["file_size_bytes"] = file_size

        # Extract metadata either from ffprobe or simulated metadata
        probe_data = self.run_ffprobe(str(path)) or simulated_meta or {}
        if not probe_data:
            details['error'] = 'ffprobe could not verify the media; install FFmpeg and supply a valid video'
            return QAReport(False, 0.0, checks, details)
        if simulated_meta is not None:
            # Explicit fixture support; the production pipeline never supplies it.
            details['simulated'] = True
            checks['no_corrupt_frames'] = True
        else:
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                try:
                    decoded = subprocess.run([ffmpeg, '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe',
                                              '-i', str(path), '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'],
                                             capture_output=True, timeout=120)
                    checks['no_corrupt_frames'] = decoded.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    pass
        checks['file_integrity'] = checks['no_corrupt_frames']

        width = 0
        height = 0
        duration = 0.0
        fps = 30.0
        v_codec = ""
        a_codec = ""
        has_audio = False

        if probe_data:
            streams = probe_data.get("streams", [])
            fmt = probe_data.get("format", {})

            for st in streams:
                codec_type = st.get("codec_type")
                if codec_type == "video":
                    width = int(st.get("width", 0))
                    height = int(st.get("height", 0))
                    v_codec = st.get("codec_name", "").lower()
                    # compute fps
                    r_frame_rate = st.get("r_frame_rate", "30/1")
                    if "/" in r_frame_rate:
                        num, den = r_frame_rate.split("/")
                        fps = float(num) / float(den) if float(den) > 0 else 30.0
                    else:
                        fps = float(r_frame_rate or 30.0)
                elif codec_type == "audio":
                    has_audio = True
                    a_codec = st.get("codec_name", "").lower()

            dur_str = fmt.get("duration") or (streams[0].get("duration") if streams else "0")
            duration = float(dur_str or 0.0)

        details["width"] = width
        details["height"] = height
        details["duration"] = duration
        details["fps"] = fps
        details["video_codec"] = v_codec
        details["audio_codec"] = a_codec

        # Check resolution & aspect ratio
        if width > 0 and height > 0:
            ratio = width / height
            target_ratio = 9.0 / 16.0
            # Allow minor rounding tolerance
            if abs(ratio - target_ratio) < 0.05 or (width == 1080 and height == 1920) or (width == 720 and height == 1280):
                checks["aspect_ratio"] = True

            if (width >= 720 and height >= 1280) and (height > width):
                checks["resolution"] = True

        # Check duration
        if self.min_duration_seconds <= duration <= self.max_duration_seconds:
            checks["duration"] = True

        # Check FPS
        if self.min_fps <= fps <= self.max_fps:
            checks["fps"] = True

        # Check codec
        if v_codec in self.allowed_video_codecs and a_codec in self.allowed_audio_codecs:
            checks["codec"] = True

        # Check audio
        if has_audio:
            checks["audio_present"] = True

        # Calculate score
        passed_count = sum(1 for v in checks.values() if v)
        total_count = len(checks)
        score = round(passed_count / total_count, 2)

        # Critical checks: file_integrity, aspect_ratio, duration, audio_present
        passed = all(checks.values())

        return QAReport(
            passed=passed,
            score=score,
            checks=checks,
            details=details,
        )
