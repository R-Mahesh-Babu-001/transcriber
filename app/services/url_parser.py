"""
URL parsing utilities for extracting YouTube video IDs from various URL formats.

Supported formats:
  - https://www.youtube.com/watch?v=VIDEO_ID
  - https://youtu.be/VIDEO_ID
  - https://www.youtube.com/shorts/VIDEO_ID
  - https://www.youtube.com/embed/VIDEO_ID
  - https://www.youtube.com/live/VIDEO_ID
  - https://m.youtube.com/watch?v=VIDEO_ID
  - https://www.youtube.com/v/VIDEO_ID
  - Bare 11-character video IDs
  - URLs with extra query parameters, timestamps, playlists, etc.
"""

import re
from urllib.parse import urlparse, parse_qs

# YouTube video IDs are exactly 11 characters: alphanumeric, hyphens, underscores
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Domains we recognise as YouTube
_YT_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

# Path prefixes that carry the video ID as the next path segment
_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/", "/e/")


def extract_video_id(url_or_id: str) -> str:
    """Extract a YouTube video ID from a URL string or bare ID.

    Args:
        url_or_id: A YouTube URL in any common format, or a bare 11-char ID.

    Returns:
        The 11-character video ID.

    Raises:
        ValueError: If the input is not a valid YouTube URL or video ID.
    """
    raw = url_or_id.strip()
    if not raw:
        raise ValueError("Input is empty.")

    # 1) Bare video ID (no slashes, no dots, exactly 11 chars)
    if VIDEO_ID_RE.match(raw) and "/" not in raw and "." not in raw:
        return raw

    # 2) Try to parse as URL
    # Add scheme if missing so urlparse works correctly
    url = raw
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host not in _YT_DOMAINS:
        raise ValueError(f"Not a recognised YouTube domain: {host!r}")

    path = parsed.path

    # 3) youtu.be/VIDEO_ID
    if host in ("youtu.be", "www.youtu.be"):
        vid = path.lstrip("/").split("/")[0].split("?")[0]
        return _validate_id(vid)

    # 4) /watch?v=VIDEO_ID
    if path in ("/watch", "/watch/"):
        qs = parse_qs(parsed.query)
        ids = qs.get("v")
        if ids:
            return _validate_id(ids[0])
        raise ValueError("Missing 'v' parameter in /watch URL.")

    # 5) /shorts/VIDEO_ID, /embed/VIDEO_ID, /live/VIDEO_ID, /v/VIDEO_ID
    for prefix in _PATH_PREFIXES:
        if path.startswith(prefix):
            vid = path[len(prefix):].split("/")[0].split("?")[0]
            return _validate_id(vid)

    raise ValueError(f"Could not extract video ID from URL: {url_or_id!r}")


def _validate_id(vid: str) -> str:
    """Validate that a string looks like a YouTube video ID."""
    vid = vid.strip()
    if VIDEO_ID_RE.match(vid):
        return vid
    raise ValueError(f"Invalid video ID: {vid!r}")
