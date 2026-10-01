"""Caption and subtitle formatting (SRT, VTT, and ASS for burn-in)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CaptionItem:
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    emphasis_words: List[str] = None

    def __post_init__(self):
        if self.emphasis_words is None:
            self.emphasis_words = []


def _format_timestamp(seconds: float, separator: str = ",", include_hours: bool = True) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    if include_hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"
    return f"{minutes:02d}:{secs:02d}{separator}{millis:03d}"


class CaptionGenerator:
    """Generates time-aligned captions with safe margin rules for 9:16 vertical video."""

    def __init__(
        self,
        max_words_per_line: int = 5,
        default_wpm: int = 150,
        bottom_margin_percent: float = 18.0,
    ):
        self.max_words_per_line = max_words_per_line
        self.default_wpm = default_wpm
        self.bottom_margin_percent = bottom_margin_percent

    def segment_script(
        self,
        script: str,
        total_duration_seconds: float,
        words_per_caption: int = 4,
    ) -> List[CaptionItem]:
        """Splits a script into timed segments proportioned across the total duration."""
        words = re.findall(r"\S+", script.strip())
        if not words:
            return []

        chunks: List[List[str]] = []
        for i in range(0, len(words), words_per_caption):
            chunks.append(words[i : i + words_per_caption])

        total_words = len(words)
        items: List[CaptionItem] = []
        elapsed = 0.0

        for idx, chunk in enumerate(chunks, start=1):
            chunk_fraction = len(chunk) / total_words
            duration = total_duration_seconds * chunk_fraction
            start = elapsed
            end = elapsed + duration
            elapsed = end

            text = " ".join(chunk)
            items.append(
                CaptionItem(
                    index=idx,
                    start_seconds=round(start, 2),
                    end_seconds=round(end, 2),
                    text=text,
                )
            )

        return items

    def to_srt(self, captions: List[CaptionItem]) -> str:
        """Exports captions to SubRip (SRT) format."""
        blocks: List[str] = []
        for item in captions:
            start_str = _format_timestamp(item.start_seconds, separator=",")
            end_str = _format_timestamp(item.end_seconds, separator=",")
            blocks.append(f"{item.index}\n{start_str} --> {end_str}\n{item.text}\n")
        return "\n".join(blocks).strip() + "\n"

    def to_vtt(self, captions: List[CaptionItem]) -> str:
        """Exports captions to WebVTT format."""
        lines = ["WEBVTT\n"]
        for item in captions:
            start_str = _format_timestamp(item.start_seconds, separator=".")
            end_str = _format_timestamp(item.end_seconds, separator=".")
            lines.append(f"{start_str} --> {end_str}\n{item.text}\n")
        return "\n".join(lines).strip() + "\n"

    def to_ass(
        self,
        captions: List[CaptionItem],
        video_width: int = 1080,
        video_height: int = 1920,
        font_name: str = "Arial",
        font_size: int = 64,
        primary_color: str = "&H00FFFFFF",
        outline_color: str = "&H00120E1A",
    ) -> str:
        """Exports captions to Advanced SubStation Alpha (ASS) format with mobile safe areas."""
        margin_v = int(video_height * (self.bottom_margin_percent / 100.0))

        header = f"""[Script Info]
Title: Spice Hoes Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []
        for item in captions:
            start_str = _format_timestamp(item.start_seconds, separator=".", include_hours=True)
            end_str = _format_timestamp(item.end_seconds, separator=".", include_hours=True)
            events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{item.text}")

        return header + "\n".join(events) + "\n"
