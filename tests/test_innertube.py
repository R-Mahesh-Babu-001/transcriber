"""
Tests for the InnerTube fallback engine in TranscriptService.
Verifies that when youtube-transcript-api is blocked (IpBlocked/RequestBlocked),
TranscriptService automatically falls back to InnerTube.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.services.transcript import TranscriptService


class FakeIpBlocked(Exception):
    pass


def test_fetch_fallback_on_ip_blocked():
    service = TranscriptService()

    # Mock primary API to raise an exception simulating IP block
    service._api.fetch = MagicMock(side_effect=FakeIpBlocked("IP blocked by YouTube"))

    # Mock _fetch_innertube to return valid transcript data
    expected_result = {
        "video_id": "wpOA-UXynoM",
        "language": "English (auto-generated)",
        "language_code": "en",
        "is_generated": True,
        "segments": [{"text": "Hello world", "start": 0.0, "duration": 2.0}],
        "plain_text": "Hello world",
        "word_count": 2,
        "char_count": 11,
    }
    service._fetch_innertube = MagicMock(return_value=expected_result)

    result = service.fetch_transcript("wpOA-UXynoM")
    assert result == expected_result
    service._fetch_innertube.assert_called_once_with("wpOA-UXynoM", language=None, translate_to=None)


def test_list_fallback_on_ip_blocked():
    service = TranscriptService()

    # Mock primary API to raise an exception simulating IP block
    service._api.list = MagicMock(side_effect=FakeIpBlocked("IP blocked by YouTube"))

    expected_list = [
        {
            "language": "English (auto-generated)",
            "language_code": "en",
            "is_generated": True,
            "is_translatable": True,
            "translation_languages": [],
        }
    ]
    service._list_innertube = MagicMock(return_value=expected_list)

    result = service.list_transcripts("wpOA-UXynoM")
    assert result == expected_list
    service._list_innertube.assert_called_once_with("wpOA-UXynoM")
