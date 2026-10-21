"""
Transcript service: wraps youtube-transcript-api v1.x with proxy support,
caching, and structured error mapping.

Library API (v1.2.4):
  - api = YouTubeTranscriptApi(proxy_config=...) — instance-based
  - api.fetch(video_id, languages=[...])          — returns FetchedTranscript
  - api.list(video_id)                            — returns TranscriptList

FetchedTranscript attributes: .snippets, .video_id, .language, .language_code, .is_generated
FetchedTranscriptSnippet attributes: .text, .start, .duration
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight TTL cache (thread-safe, size-capped)
# ---------------------------------------------------------------------------
@dataclass
class _CacheEntry:
    data: Any
    expires: float


class TTLCache:
    """Simple in-memory cache with TTL and max-size eviction (FIFO)."""

    def __init__(self, ttl: int = 300, max_size: int = 100):
        self._ttl = ttl
        self._max = max_size
        self._store: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry.expires:
                del self._store[key]
                return None
            return entry.data

    def set(self, key: str, data: Any) -> None:
        with self._lock:
            # Evict oldest if at capacity
            while len(self._store) >= self._max:
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[key] = _CacheEntry(data=data, expires=time.time() + self._ttl)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Proxy configuration from environment
# ---------------------------------------------------------------------------
def _build_proxy_config():
    """Build proxy config from env vars. Returns None if nothing is set."""
    # Webshare takes priority
    ws_user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    ws_pass = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if ws_user and ws_pass:
        location = os.environ.get("WEBSHARE_PROXY_LOCATION", "US")
        logger.info("Using Webshare proxy (location=%s)", location)
        return WebshareProxyConfig(
            username=ws_user,
            password=ws_pass,
            location=location,
        )

    # Generic proxy
    http_proxy = os.environ.get("GENERIC_HTTP_PROXY")
    https_proxy = os.environ.get("GENERIC_HTTPS_PROXY")
    if http_proxy or https_proxy:
        logger.info("Using generic proxy")
        return GenericProxyConfig(
            http_url=http_proxy or "",
            https_url=https_proxy or "",
        )

    logger.warning(
        "No proxy configured. YouTube may block datacenter IPs. "
        "Set WEBSHARE_PROXY_USERNAME/PASSWORD or GENERIC_HTTP_PROXY/GENERIC_HTTPS_PROXY."
    )
    return None


# ---------------------------------------------------------------------------
# Transcript service (singleton-ish, constructed once in main.py)
# ---------------------------------------------------------------------------
class TranscriptService:
    """High-level wrapper around YouTubeTranscriptApi."""

    def __init__(self, cache_ttl: int = 300, cache_max: int = 100):
        proxy_config = _build_proxy_config()
        kwargs: dict[str, Any] = {}
        if proxy_config is not None:
            kwargs["proxy_config"] = proxy_config
        self._api = YouTubeTranscriptApi(**kwargs)
        self._cache = TTLCache(ttl=cache_ttl, max_size=cache_max)

    # ---- List available transcripts ----
    def list_transcripts(self, video_id: str) -> list[dict]:
        """Return metadata about all available transcripts for a video.

        Each item:
          { language, language_code, is_generated, is_translatable, translation_languages }
        """
        cache_key = f"list:{video_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        transcript_list = self._api.list(video_id)
        results: list[dict] = []
        for t in transcript_list:
            results.append({
                "language": t.language,
                "language_code": t.language_code,
                "is_generated": t.is_generated,
                "is_translatable": t.is_translatable,
                "translation_languages": [
                    {"language": tl.get("language", tl.get("language_code", "")),
                     "language_code": tl.get("language_code", tl.get("language", ""))}
                    for tl in (t.translation_languages if hasattr(t, "translation_languages") else [])
                ],
            })
        self._cache.set(cache_key, results)
        return results

    # ---- Fetch transcript ----
    def fetch_transcript(
        self,
        video_id: str,
        language: str | None = None,
        translate_to: str | None = None,
    ) -> dict:
        """Fetch transcript for a video. Returns structured data.

        Returns:
            {
                video_id, language, language_code, is_generated,
                segments: [{text, start, duration}, ...],
                plain_text, word_count, char_count
            }
        """
        cache_key = f"fetch:{video_id}:{language or ''}:{translate_to or ''}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if translate_to:
            # Need to go through list → find → translate → fetch
            transcript_list = self._api.list(video_id)
            langs = [language] if language else ["en"]
            transcript = transcript_list.find_transcript(langs)
            if not transcript.is_translatable:
                raise ValueError(
                    f"Transcript in '{transcript.language_code}' is not translatable."
                )
            translated = transcript.translate(translate_to)
            fetched = translated.fetch()
        else:
            langs = [language] if language else ["en"]
            fetched = self._api.fetch(video_id, languages=langs)

        # Build segments from FetchedTranscriptSnippets
        segments = []
        text_parts = []
        for snippet in fetched:
            segments.append({
                "text": snippet.text,
                "start": snippet.start,
                "duration": snippet.duration,
            })
            text_parts.append(snippet.text)

        plain_text = " ".join(text_parts)
        word_count = len(plain_text.split())
        char_count = len(plain_text)

        result = {
            "video_id": fetched.video_id,
            "language": fetched.language,
            "language_code": fetched.language_code,
            "is_generated": fetched.is_generated,
            "segments": segments,
            "plain_text": plain_text,
            "word_count": word_count,
            "char_count": char_count,
        }
        self._cache.set(cache_key, result)
        return result
