#!/usr/bin/env python3
"""
whisper_fallback.py — LOCAL-ONLY fallback for videos with no captions.

Uses yt-dlp to download audio and openai-whisper to transcribe it locally.

⚠️  NOT runnable on Render's free tier (512MB RAM, no GPU).
    Whisper 'base' model needs ~1GB RAM; 'tiny' may work but quality is poor.

Requirements (NOT in requirements.txt):
    pip install yt-dlp openai-whisper

Usage:
    python whisper_fallback.py "https://www.youtube.com/watch?v=VIDEO_ID" [--model base] [--output transcript.txt]
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def download_audio(url: str, output_dir: str) -> str:
    """Download audio using yt-dlp, return path to the audio file."""
    output_template = str(Path(output_dir) / "audio.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",  # medium quality, smaller file
        "-o", output_template,
        url,
    ]
    print(f"[yt-dlp] Downloading audio...")
    subprocess.run(cmd, check=True)

    # Find the downloaded file
    audio_files = list(Path(output_dir).glob("audio.*"))
    if not audio_files:
        raise FileNotFoundError("yt-dlp did not produce an audio file.")
    return str(audio_files[0])


def transcribe_audio(audio_path: str, model_name: str = "base") -> str:
    """Transcribe audio using OpenAI Whisper."""
    try:
        import whisper
    except ImportError:
        print("ERROR: openai-whisper is not installed. Run: pip install openai-whisper")
        sys.exit(1)

    print(f"[whisper] Loading model '{model_name}'...")
    model = whisper.load_model(model_name)
    print(f"[whisper] Transcribing...")
    result = model.transcribe(audio_path)
    return result["text"]


def main():
    parser = argparse.ArgumentParser(
        description="Local-only transcript fallback using yt-dlp + Whisper."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--model", default="base", help="Whisper model: tiny, base, small, medium, large")
    parser.add_argument("--output", "-o", default=None, help="Output file path (prints to stdout if not set)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = download_audio(args.url, tmpdir)
        transcript = transcribe_audio(audio_path, model_name=args.model)

    if args.output:
        Path(args.output).write_text(transcript, encoding="utf-8")
        print(f"Transcript saved to {args.output}")
    else:
        print("\n--- Transcript ---\n")
        print(transcript)


if __name__ == "__main__":
    main()
