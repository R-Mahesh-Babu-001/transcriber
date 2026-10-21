"""
Server-side exporters: convert transcript segments to TXT, SRT, VTT, JSON, and Markdown.
No truncation anywhere.
"""

from __future__ import annotations

import json
from typing import Any


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as VTT timestamp: HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _format_timestamp_readable(seconds: float) -> str:
    """Format seconds as [HH:MM:SS] for display."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def export_txt(segments: list[dict], include_timestamps: bool = False) -> str:
    """Export as plain text."""
    lines = []
    for seg in segments:
        if include_timestamps:
            lines.append(f"{_format_timestamp_readable(seg['start'])} {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)


def export_srt(segments: list[dict]) -> str:
    """Export as SubRip (.srt) format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg["start"])
        end = _format_timestamp_srt(seg["start"] + seg["duration"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")  # blank line separator
    return "\n".join(lines)


def export_vtt(segments: list[dict]) -> str:
    """Export as WebVTT (.vtt) format."""
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = _format_timestamp_vtt(seg["start"])
        end = _format_timestamp_vtt(seg["start"] + seg["duration"])
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def export_json(transcript_data: dict) -> str:
    """Export the full transcript data as pretty-printed JSON."""
    return json.dumps(transcript_data, indent=2, ensure_ascii=False)


def export_markdown(
    segments: list[dict],
    video_id: str = "",
    language: str = "",
    include_timestamps: bool = True,
) -> str:
    """Export as Markdown with optional metadata header."""
    lines = [f"# Transcript"]
    if video_id:
        lines.append(f"\n**Video:** https://www.youtube.com/watch?v={video_id}")
    if language:
        lines.append(f"**Language:** {language}")
    lines.append("")
    lines.append("---")
    lines.append("")
    for seg in segments:
        if include_timestamps:
            ts = _format_timestamp_readable(seg["start"])
            lines.append(f"**{ts}** {seg['text']}  ")
        else:
            lines.append(f"{seg['text']}  ")
    return "\n".join(lines)
