"""
Tests for the error mapping module.
Uses mock exceptions to verify correct HTTP status codes and messages.
"""

import pytest
from app.services.errors import map_exception


class FakeException(Exception):
    """Base for fake exceptions mimicking the library's hierarchy."""
    pass


def _make_fake(name: str):
    """Create a simple exception class with the given name."""
    return type(name, (FakeException,), {})


class TestErrorMapping:
    """
    Test that known exception types map to the expected status codes.
    We monkey-patch the module's exception references to use our fakes.
    """

    def _patch_and_test(self, exc_attr: str, expected_status: int, expected_type: str):
        """Helper: temporarily set the module-level exception type and test."""
        import app.services.errors as err_mod
        FakeExc = _make_fake(exc_attr)
        original = getattr(err_mod, exc_attr, None)
        try:
            setattr(err_mod, exc_attr, FakeExc)
            status, error_type, message = map_exception(FakeExc("test"))
            assert status == expected_status, f"Expected {expected_status} for {exc_attr}, got {status}"
            assert error_type == expected_type
            assert isinstance(message, str)
            assert len(message) > 0
        finally:
            setattr(err_mod, exc_attr, original)

    def test_ip_blocked(self):
        self._patch_and_test("IpBlocked", 403, "ip_blocked")

    def test_request_blocked(self):
        self._patch_and_test("RequestBlocked", 403, "ip_blocked")

    def test_too_many_requests(self):
        self._patch_and_test("TooManyRequests", 429, "rate_limited")

    def test_video_unavailable(self):
        self._patch_and_test("VideoUnavailable", 404, "video_unavailable")

    def test_age_restricted(self):
        self._patch_and_test("AgeRestricted", 403, "age_restricted")

    def test_not_translatable(self):
        self._patch_and_test("NotTranslatable", 400, "not_translatable")

    def test_youtube_request_failed(self):
        self._patch_and_test("YouTubeRequestFailed", 502, "youtube_request_failed")

    def test_unknown_exception_fallback(self):
        """Unrecognised exceptions should map to 500."""
        status, error_type, message = map_exception(RuntimeError("something broke"))
        assert status == 500
        assert error_type == "internal_error"
