"""
Error mapping: translates youtube-transcript-api exceptions into
(status_code, human-readable message) tuples.
"""

from __future__ import annotations

import logging

# Import all known exception types from the library (v1.2.4).
# Some may not exist in every version, so we import defensively.
try:
    from youtube_transcript_api import (
        TranscriptsDisabled,
        NoTranscriptFound,
    )
except ImportError:
    TranscriptsDisabled = None  # type: ignore[misc,assignment]
    NoTranscriptFound = None  # type: ignore[misc,assignment]

_OPTIONAL_EXCEPTIONS: dict[str, type | None] = {}
for _name in (
    "VideoUnavailable",
    "VideoUnplayable",
    "AgeRestricted",
    "TooManyRequests",
    "IpBlocked",
    "RequestBlocked",
    "NoTranscriptAvailable",
    "NotTranslatable",
    "TranslationLanguageNotAvailable",
    "YouTubeRequestFailed",
    "InvalidVideoId",
    "FailedToCreateConsentCookie",
):
    try:
        import youtube_transcript_api as _ytt
        _OPTIONAL_EXCEPTIONS[_name] = getattr(_ytt, _name, None)
    except Exception:
        _OPTIONAL_EXCEPTIONS[_name] = None

logger = logging.getLogger(__name__)

# Pre-resolve for fast isinstance checks
VideoUnavailable = _OPTIONAL_EXCEPTIONS.get("VideoUnavailable")
VideoUnplayable = _OPTIONAL_EXCEPTIONS.get("VideoUnplayable")
AgeRestricted = _OPTIONAL_EXCEPTIONS.get("AgeRestricted")
TooManyRequests = _OPTIONAL_EXCEPTIONS.get("TooManyRequests")
IpBlocked = _OPTIONAL_EXCEPTIONS.get("IpBlocked")
RequestBlocked = _OPTIONAL_EXCEPTIONS.get("RequestBlocked")
NoTranscriptAvailable = _OPTIONAL_EXCEPTIONS.get("NoTranscriptAvailable")
NotTranslatable = _OPTIONAL_EXCEPTIONS.get("NotTranslatable")
TranslationLanguageNotAvailable = _OPTIONAL_EXCEPTIONS.get("TranslationLanguageNotAvailable")
YouTubeRequestFailed = _OPTIONAL_EXCEPTIONS.get("YouTubeRequestFailed")
InvalidVideoId = _OPTIONAL_EXCEPTIONS.get("InvalidVideoId")
FailedToCreateConsentCookie = _OPTIONAL_EXCEPTIONS.get("FailedToCreateConsentCookie")


def _is_instance_safe(exc: Exception, exc_type: type | None) -> bool:
    """isinstance check that handles None types gracefully."""
    if exc_type is None:
        return False
    return isinstance(exc, exc_type)


def map_exception(exc: Exception) -> tuple[int, str, str]:
    """Map a library exception to (status_code, error_type, user_message).

    Returns:
        Tuple of (HTTP status code, error type string, user-facing message).
    """
    # IP / request blocking — the most important case for cloud deployments
    if _is_instance_safe(exc, IpBlocked) or _is_instance_safe(exc, RequestBlocked):
        logger.warning(
            "YouTube blocked this request (IP block). "
            "Consider configuring a proxy via WEBSHARE_PROXY_USERNAME/PASSWORD."
        )
        return (
            403,
            "ip_blocked",
            "YouTube is blocking requests from this server's IP address. "
            "This typically happens on cloud/datacenter IPs. "
            "The site owner needs to configure a proxy. "
            "Try again later, or use a different instance.",
        )

    if _is_instance_safe(exc, TooManyRequests):
        return (
            429,
            "rate_limited",
            "YouTube is rate-limiting requests. Please try again in a few minutes.",
        )

    if _is_instance_safe(exc, TranscriptsDisabled) or (TranscriptsDisabled and isinstance(exc, TranscriptsDisabled)):
        return (
            404,
            "transcripts_disabled",
            "Subtitles/transcripts are disabled for this video by the creator.",
        )

    if _is_instance_safe(exc, NoTranscriptAvailable):
        return (
            404,
            "no_transcript_available",
            "No transcripts are available for this video at all.",
        )

    if (NoTranscriptFound and isinstance(exc, NoTranscriptFound)):
        return (
            404,
            "no_transcript_found",
            "No transcript was found for the requested language. "
            "Try a different language or check available languages.",
        )

    if _is_instance_safe(exc, VideoUnavailable):
        return (
            404,
            "video_unavailable",
            "This video is unavailable (it may be private, deleted, or region-locked).",
        )

    if _is_instance_safe(exc, VideoUnplayable):
        return (
            404,
            "video_unplayable",
            "This video cannot be played (it may be an upcoming or live stream).",
        )

    if _is_instance_safe(exc, AgeRestricted):
        return (
            403,
            "age_restricted",
            "This video is age-restricted and cannot be accessed without authentication.",
        )

    if _is_instance_safe(exc, NotTranslatable):
        return (
            400,
            "not_translatable",
            "The requested transcript cannot be translated to the target language.",
        )

    if _is_instance_safe(exc, TranslationLanguageNotAvailable):
        return (
            400,
            "translation_language_not_available",
            "The requested translation language is not available for this transcript.",
        )

    if _is_instance_safe(exc, InvalidVideoId):
        return (
            400,
            "invalid_video_id",
            "The provided video ID is invalid.",
        )

    if _is_instance_safe(exc, YouTubeRequestFailed):
        return (
            502,
            "youtube_request_failed",
            "A request to YouTube failed unexpectedly. Please try again.",
        )

    if _is_instance_safe(exc, FailedToCreateConsentCookie):
        return (
            502,
            "consent_cookie_failed",
            "Failed to handle YouTube consent flow. Please try again.",
        )

    # Fallback for any other library exception
    logger.error("Unmapped exception: %s: %s", type(exc).__name__, exc)
    return (
        500,
        "internal_error",
        "An unexpected error occurred while fetching the transcript.",
    )
