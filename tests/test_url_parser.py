"""
Tests for URL parsing / video ID extraction.
Covers all URL formats listed in the requirements + rejection of invalid input.
"""

import pytest
from app.services.url_parser import extract_video_id


# ---- Valid URLs and IDs ----

class TestValidUrls:
    """Every supported YouTube URL format should be correctly parsed."""

    def test_standard_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120&list=PLxyz") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url_with_params(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=42") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self):
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_v_url(self):
        assert extract_video_id("https://www.youtube.com/v/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_mobile_url(self):
        assert extract_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_music_url(self):
        assert extract_video_id("https://music.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_no_scheme(self):
        assert extract_video_id("www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_http_scheme(self):
        assert extract_video_id("http://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_bare_video_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_bare_id_with_hyphens_and_underscores(self):
        assert extract_video_id("_Ab-12_cd-E") == "_Ab-12_cd-E"

    def test_whitespace_stripping(self):
        assert extract_video_id("  dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"

    def test_embed_with_trailing_slash(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ/") == "dQw4w9WgXcQ"

    def test_shorts_with_query(self):
        assert extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"

    def test_e_url(self):
        """The /e/ shorthand embed format."""
        assert extract_video_id("https://www.youtube.com/e/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


# ---- Invalid inputs ----

class TestInvalidInputs:
    """Malformed URLs and non-YouTube domains must be rejected."""

    def test_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            extract_video_id("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="empty"):
            extract_video_id("   ")

    def test_random_url(self):
        with pytest.raises(ValueError, match="Not a recognised YouTube"):
            extract_video_id("https://www.example.com/watch?v=dQw4w9WgXcQ")

    def test_too_short_id(self):
        with pytest.raises(ValueError):
            extract_video_id("abc123")

    def test_too_long_id(self):
        with pytest.raises(ValueError):
            extract_video_id("dQw4w9WgXcQextra")

    def test_invalid_chars_in_id(self):
        with pytest.raises(ValueError):
            extract_video_id("dQw4w9WgX!Q")

    def test_watch_without_v_param(self):
        with pytest.raises(ValueError, match="Missing 'v' parameter"):
            extract_video_id("https://www.youtube.com/watch?list=PLxyz")

    def test_non_youtube_domain(self):
        with pytest.raises(ValueError, match="Not a recognised"):
            extract_video_id("https://vimeo.com/12345")

    def test_youtube_but_no_path(self):
        with pytest.raises(ValueError):
            extract_video_id("https://www.youtube.com/")
