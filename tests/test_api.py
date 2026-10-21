"""
Tests for the API endpoints using FastAPI's TestClient.
Mocks the transcript service to avoid real YouTube calls.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---- Health check ----

class TestHealthz:
    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---- GET / (frontend) ----

class TestFrontend:
    def test_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "YouTube Transcriber" in resp.text


# ---- POST /api/transcript ----

class TestTranscriptEndpoint:
    def test_invalid_url(self, client):
        resp = client.post("/api/transcript", json={"url": ""})
        assert resp.status_code == 400

    def test_non_youtube_url(self, client):
        resp = client.post("/api/transcript", json={"url": "https://example.com"})
        assert resp.status_code == 400

    @patch("app.main.transcript_service")
    def test_successful_fetch(self, mock_service, client):
        mock_service.fetch_transcript.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "language": "English",
            "language_code": "en",
            "is_generated": False,
            "segments": [{"text": "hello", "start": 0.0, "duration": 1.5}],
            "plain_text": "hello",
            "word_count": 1,
            "char_count": 5,
        }
        resp = client.post("/api/transcript", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert len(data["segments"]) == 1

    @patch("app.main.transcript_service")
    def test_library_exception_mapping(self, mock_service, client):
        """When the library raises an exception, it should be mapped to a clean error."""
        # Simulate a generic exception (will map to 500)
        mock_service.fetch_transcript.side_effect = RuntimeError("Something broke")
        resp = client.post("/api/transcript", json={"url": "dQw4w9WgXcQ"})
        assert resp.status_code == 500
        data = resp.json()
        assert "detail" in data


# ---- GET /api/languages ----

class TestLanguagesEndpoint:
    def test_missing_url(self, client):
        resp = client.get("/api/languages")
        assert resp.status_code == 422  # FastAPI validation error

    def test_invalid_url(self, client):
        resp = client.get("/api/languages?url=notaurl")
        assert resp.status_code == 400

    @patch("app.main.transcript_service")
    def test_successful_list(self, mock_service, client):
        mock_service.list_transcripts.return_value = [
            {
                "language": "English",
                "language_code": "en",
                "is_generated": False,
                "is_translatable": True,
                "translation_languages": [],
            }
        ]
        resp = client.get("/api/languages?url=dQw4w9WgXcQ")
        assert resp.status_code == 200
        data = resp.json()
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert len(data["transcripts"]) == 1


# ---- POST /api/export ----

class TestExportEndpoint:
    @patch("app.main.transcript_service")
    def test_export_txt(self, mock_service, client):
        mock_service.fetch_transcript.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "language": "English",
            "language_code": "en",
            "is_generated": False,
            "segments": [{"text": "hello world", "start": 0.0, "duration": 2.0}],
            "plain_text": "hello world",
            "word_count": 2,
            "char_count": 11,
        }
        resp = client.post("/api/export", json={"url": "dQw4w9WgXcQ", "format": "txt"})
        assert resp.status_code == 200
        assert "hello world" in resp.text

    @patch("app.main.transcript_service")
    def test_export_srt(self, mock_service, client):
        mock_service.fetch_transcript.return_value = {
            "video_id": "dQw4w9WgXcQ",
            "language": "English",
            "language_code": "en",
            "is_generated": False,
            "segments": [{"text": "hello", "start": 0.0, "duration": 1.0}],
            "plain_text": "hello",
            "word_count": 1,
            "char_count": 5,
        }
        resp = client.post("/api/export", json={"url": "dQw4w9WgXcQ", "format": "srt"})
        assert resp.status_code == 200
        assert "-->" in resp.text

    def test_export_invalid_format(self, client):
        with patch("app.main.transcript_service") as mock_service:
            mock_service.fetch_transcript.return_value = {
                "video_id": "dQw4w9WgXcQ",
                "segments": [],
                "plain_text": "",
                "word_count": 0,
                "char_count": 0,
            }
            resp = client.post("/api/export", json={"url": "dQw4w9WgXcQ", "format": "pdf"})
            assert resp.status_code == 400
