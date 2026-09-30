"""Zero-cost production toolchain described by the project guide.

Browser-only generators are represented as auditable tasks rather than pretending
there is a free unattended API. Local assembly uses FFmpeg when installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProductionTask:
    stage: str
    tool: str
    mode: str
    instructions: str
    cost_cents: int = 0


FREE_TOOLS = {
    "image": "Local Dream HTTP (S24 Ultra)",
    "upscale": "Local Dream upscaler / native output",
    "motion": "Google Flow / VEO 3.1 Fast",
    "avatar": "Pavo AI",
    "orchestrator": "n8n Community Edition",
    "assembly": "FFmpeg",
}


def free_production_plan(brief: dict, use_avatar: bool = False) -> list[dict]:
    """Turn a creative brief into the guide's free production workflow."""
    prompt = brief["prompt"]
    tasks = [
        ProductionTask(
            "image", FREE_TOOLS["image"], "browser",
            "Generate the production still on the S24 Ultra through Local Dream HTTP. Prompt: " + prompt,
        ),
        ProductionTask(
            "upscale", FREE_TOOLS["upscale"], "browser",
            "Keep generation/upscaling on-device with Local Dream; record the resulting asset URI and generation lineage.",
        ),
    ]
    if use_avatar:
        tasks.append(ProductionTask(
            "motion", FREE_TOOLS["avatar"], "browser",
            "Create a 12-second 720p talking clip from the approved character image; keep voice/language settings consistent.",
        ))
    else:
        tasks.append(ProductionTask(
            "motion", FREE_TOOLS["motion"], "browser",
            "Use Frames to Video with the upscaled still as the initial frame; request natural camera and body motion.",
        ))
    tasks.extend([
        ProductionTask(
            "assembly", FREE_TOOLS["assembly"], "local",
            "Join approved clips and burn captions locally with FFmpeg.",
        ),
        ProductionTask(
            "orchestration", FREE_TOOLS["orchestrator"], "local",
            "Track tasks, approvals, asset paths, publishing handoff, and outcome imports in self-hosted n8n.",
        ),
    ])
    return [asdict(task) for task in tasks]


def write_job(brief: dict, output: str | Path, use_avatar: bool = False) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"brief": brief, "production": free_production_plan(brief, use_avatar)}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def assemble_vertical(clips: list[str], output: str, captions: str | None = None) -> str:
    """Assemble clips with the locally installed free FFmpeg binary."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed or not on PATH")
    if not clips:
        raise ValueError("At least one clip is required")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = out.with_suffix(out.suffix + ".concat.txt")
    manifest.write_text("".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips))

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest)]
    if captions:
        escaped = str(Path(captions).resolve()).replace("\\", "/").replace(":", "\\:")
        cmd += ["-vf", f"subtitles='{escaped}'", "-c:v", "libx264", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]
    cmd.append(str(out))
    subprocess.run(cmd, check=True)
    return str(out)
