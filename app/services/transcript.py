"""
Transcript service: wraps youtube-transcript-api v1.x with proxy support,
caching, and structured error mapping, with an automatic fallback to
YouTube's InnerTube Android client to bypass cloud/datacenter IP blocks (Render, AWS, etc.).

Library API (v1.2.4):
  - api = YouTubeTranscriptApi(proxy_config=...) — instance-based
  - api.fetch(video_id, languages=[...])          — returns FetchedTranscript
  - api.list(video_id)                            — returns TranscriptList

FetchedTranscript attributes: .snippets, .video_id, .language, .language_code, .is_generated
FetchedTranscriptSnippet attributes: .text, .start, .duration
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from threading import Lock
from typing import Any

import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

# Optional imports for specific exception types
try:
    from youtube_transcript_api import VideoUnavailable
except ImportError:
    VideoUnavailable = None  # type: ignore[misc,assignment]

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
        "InnerTube Android engine will automatically serve as fallback."
    )
    return None


def _get_requests_proxies() -> dict[str, str] | None:
    """Return proxies dictionary for requests if configured in env vars."""
    http_proxy = os.environ.get("GENERIC_HTTP_PROXY")
    https_proxy = os.environ.get("GENERIC_HTTPS_PROXY")
    if http_proxy or https_proxy:
        return {"http": http_proxy or "", "https": https_proxy or http_proxy or ""}

    ws_user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    ws_pass = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if ws_user and ws_pass:
        proxy_url = f"http://{ws_user}:{ws_pass}@p.webshare.io:80"
        return {"http": proxy_url, "https": proxy_url}

    return None


# ---------------------------------------------------------------------------
# Transcript service with automatic InnerTube Android fallback
# ---------------------------------------------------------------------------
class TranscriptService:
    """High-level wrapper around YouTubeTranscriptApi + InnerTube Android fallback."""

    def __init__(self, cache_ttl: int = 300, cache_max: int = 100):
        proxy_config = _build_proxy_config()
        kwargs: dict[str, Any] = {}
        if proxy_config is not None:
            kwargs["proxy_config"] = proxy_config
        self._api = YouTubeTranscriptApi(**kwargs)
        self._cache = TTLCache(ttl=cache_ttl, max_size=cache_max)

    # -----------------------------------------------------------------------
    # InnerTube Android Client Engine (Datacenter IP unblocker)
    # -----------------------------------------------------------------------
    def _call_innertube_player(self, video_id: str, lang: str | None = None) -> dict:
        """Call YouTube's official InnerTube API with Android client context."""
        url = "https://www.youtube.com/youtubei/v1/player"
        payload = {
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "20.10.38",
                    "hl": lang or "en",
                    "gl": "US",
                }
            },
            "videoId": video_id,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14)",
        }
        proxies = _get_requests_proxies()
        resp = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        playability = data.get("playabilityStatus", {})
        status = playability.get("status")
        if status in ("ERROR", "UNPLAYABLE", "LOGIN_REQUIRED"):
            reason = playability.get("reason", "Video is unavailable.")
            if VideoUnavailable:
                raise VideoUnavailable(video_id)
            raise ValueError(reason)

        return data

    def _list_innertube(self, video_id: str) -> list[dict]:
        """List transcripts using InnerTube."""
        data = self._call_innertube_player(video_id)
        captions_renderer = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
        caption_tracks = captions_renderer.get("captionTracks", [])
        if not caption_tracks:
            raise TranscriptsDisabled(video_id)

        results: list[dict] = []
        for t in caption_tracks:
            track_name = t.get("name", {}).get("runs", [{}])[0].get("text", t.get("languageCode", ""))
            is_gen = t.get("kind") == "asr" or "auto" in track_name.lower() or t.get("vssId", "").startswith("a.")
            results.append({
                "language": track_name,
                "language_code": t.get("languageCode", ""),
                "is_generated": is_gen,
                "is_translatable": t.get("isTranslatable", False),
                "translation_languages": [],
            })
        return results

    def _fetch_innertube(
        self,
        video_id: str,
        language: str | None = None,
        translate_to: str | None = None,
    ) -> dict:
        """Fetch transcript using InnerTube (bypasses datacenter web scraping blocks)."""
        target_lang = translate_to or language
        data = self._call_innertube_player(video_id, lang=target_lang)
        captions_renderer = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
        caption_tracks = captions_renderer.get("captionTracks", [])
        if not caption_tracks:
            raise TranscriptsDisabled(video_id)

        selected_track = None
        if target_lang:
            for t in caption_tracks:
                code = t.get("languageCode", "")
                if code == target_lang or code.startswith(target_lang + "-") or code.startswith(target_lang + "_"):
                    selected_track = t
                    break

        if not selected_track:
            en_manual = [t for t in caption_tracks if t.get("languageCode") == "en" and t.get("kind") != "asr"]
            en_auto = [t for t in caption_tracks if t.get("languageCode") == "en"]
            any_manual = [t for t in caption_tracks if t.get("kind") != "asr"]
            if en_manual:
                selected_track = en_manual[0]
            elif en_auto:
                selected_track = en_auto[0]
            elif any_manual:
                selected_track = any_manual[0]
            else:
                selected_track = caption_tracks[0]

        base_url = selected_track["baseUrl"]
        if "fmt=" in base_url:
            json_url = re.sub(r"fmt=[^&]+", "fmt=json3", base_url)
        else:
            json_url = base_url + "&fmt=json3"

        headers = {"User-Agent": "Mozilla/5.0"}
        proxies = _get_requests_proxies()
        segments: list[dict] = []
        text_parts: list[str] = []

        try:
            sub_resp = requests.get(json_url, headers=headers, proxies=proxies, timeout=12)
            sub_data = sub_resp.json()
            events = sub_data.get("events", [])
            for ev in events:
                segs = ev.get("segs")
                if not segs:
                    continue
                text = html.unescape("".join(s.get("utf8", "") for s in segs)).replace("\n", " ").strip()
                if not text:
                    continue
                start = ev.get("tStartMs", 0) / 1000.0
                dur = ev.get("dDurationMs", 0) / 1000.0
                segments.append({"text": text, "start": start, "duration": dur})
                text_parts.append(text)
        except Exception:
            # Fallback to XML parsing if json3 is not available
            xml_resp = requests.get(base_url, headers=headers, proxies=proxies, timeout=12)
            root = ET.fromstring(xml_resp.text)
            for elem in root.iter("p"):
                t_ms = float(elem.attrib.get("t", 0))
                d_ms = float(elem.attrib.get("d", 0))
                text = "".join(elem.itertext()).strip()
                if text:
                    text = html.unescape(text).replace("\n", " ")
                    segments.append({"text": text, "start": t_ms / 1000.0, "duration": d_ms / 1000.0})
                    text_parts.append(text)

        plain_text = " ".join(text_parts)
        track_name = selected_track.get("name", {}).get("runs", [{}])[0].get("text", selected_track.get("languageCode"))
        is_generated = selected_track.get("kind") == "asr" or "auto" in track_name.lower() or selected_track.get("vssId", "").startswith("a.")

        return {
            "video_id": video_id,
            "language": track_name,
            "language_code": selected_track.get("languageCode"),
            "is_generated": is_generated,
            "segments": segments,
            "plain_text": plain_text,
            "word_count": len(plain_text.split()),
            "char_count": len(plain_text),
        }

    # -----------------------------------------------------------------------
    # Public APIs (cached + dual engine)
    # -----------------------------------------------------------------------
    def list_transcripts(self, video_id: str) -> list[dict]:
        """Return metadata about all available transcripts for a video."""
        cache_key = f"list:{video_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            transcript_list = self._api.list(video_id)
            results: list[dict] = []
            for t in transcript_list:
                results.append({
                    "language": t.language,
                    "language_code": t.language_code,
                    "is_generated": t.is_generated,
                    "is_translatable": t.is_translatable,
                    "translation_languages": [
                        {
                            "language": getattr(tl, "language", tl.get("language", "") if isinstance(tl, dict) else str(tl)),
                            "language_code": getattr(tl, "language_code", tl.get("language_code", "") if isinstance(tl, dict) else str(tl)),
                        }
                        for tl in (t.translation_languages if hasattr(t, "translation_languages") else [])
                    ],
                })
        except Exception as e:
            logger.warning(
                "Primary list_transcripts failed (%s: %s). Falling back to InnerTube engine for %s",
                type(e).__name__, e, video_id
            )
            try:
                results = self._list_innertube(video_id)
            except Exception as inner_err:
                logger.error("InnerTube list fallback also failed: %s", inner_err)
                raise e

        self._cache.set(cache_key, results)
        return results

    def fetch_transcript(
        self,
        video_id: str,
        language: str | None = None,
        translate_to: str | None = None,
    ) -> dict:
        """Fetch transcript for a video with automatic InnerTube fallback."""
        cache_key = f"fetch:{video_id}:{language or ''}:{translate_to or ''}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            if translate_to:
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
        except Exception as e:
            logger.warning(
                "Primary fetch_transcript failed (%s: %s). Falling back to InnerTube engine for %s",
                type(e).__name__, e, video_id
            )
            try:
                result = self._fetch_innertube(
                    video_id,
                    language=language,
                    translate_to=translate_to,
                )
            except Exception as inner_err:
                logger.error("InnerTube fetch fallback also failed: %s", inner_err)
                raise e

        self._cache.set(cache_key, result)
        return result
