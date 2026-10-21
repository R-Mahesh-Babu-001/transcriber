"""
YouTube Transcriber — FastAPI application.

Single-file server that serves the static frontend and provides API endpoints
for fetching and exporting YouTube transcripts.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.errors import map_exception
from app.services.exporters import (
    export_json,
    export_markdown,
    export_srt,
    export_txt,
    export_vtt,
)
from app.services.transcript import TranscriptService
from app.services.url_parser import extract_video_id

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("transcriber")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="YouTube Transcriber",
    version="1.0.0",
    docs_url=None,  # Disable Swagger in production
    redoc_url=None,
)

# CORS — locked to same-origin by default
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
if allowed_origins:
    origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
else:
    origins = []  # Same-origin only

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Transcript service (singleton)
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
CACHE_MAX = int(os.environ.get("CACHE_MAX_SIZE", "100"))
transcript_service = TranscriptService(cache_ttl=CACHE_TTL, cache_max=CACHE_MAX)

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per IP)
# ---------------------------------------------------------------------------
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))
INPUT_MAX_LEN = 2048  # Max URL length accepted

_rate_lock = Lock()
_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    window = 60.0
    with _rate_lock:
        timestamps = _rate_store[client_ip]
        # Purge old entries
        _rate_store[client_ip] = [t for t in timestamps if now - t < window]
        if len(_rate_store[client_ip]) >= RATE_LIMIT:
            return False
        _rate_store[client_ip].append(now)
        return True


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For from trusted proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class TranscriptRequest(BaseModel):
    url: str = Field(..., max_length=INPUT_MAX_LEN, description="YouTube URL or video ID")
    language: str | None = Field(None, max_length=10, description="Language code (e.g., 'en', 'es')")
    include_timestamps: bool = Field(True, description="Include timestamps in text export")
    translate_to: str | None = Field(None, max_length=10, description="Translate to this language code")


class ExportRequest(BaseModel):
    url: str = Field(..., max_length=INPUT_MAX_LEN)
    language: str | None = None
    translate_to: str | None = None
    format: str = Field("txt", description="Export format: txt, srt, vtt, json, md")
    include_timestamps: bool = True


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API: List available languages
# ---------------------------------------------------------------------------
@app.get("/api/languages")
async def get_languages(url: str, request: Request):
    """List available transcripts (manual + auto) for a video."""
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, detail="Rate limit exceeded. Please wait a minute.")

    if len(url) > INPUT_MAX_LEN:
        raise HTTPException(400, detail="URL too long.")

    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    try:
        transcripts = transcript_service.list_transcripts(video_id)
    except Exception as e:
        status, error_type, message = map_exception(e)
        raise HTTPException(status, detail={"error": error_type, "message": message})

    return {"video_id": video_id, "transcripts": transcripts}


# ---------------------------------------------------------------------------
# API: Fetch transcript
# ---------------------------------------------------------------------------
@app.post("/api/transcript")
async def get_transcript(body: TranscriptRequest, request: Request):
    """Fetch the full transcript for a video."""
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, detail="Rate limit exceeded. Please wait a minute.")

    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    try:
        result = transcript_service.fetch_transcript(
            video_id,
            language=body.language,
            translate_to=body.translate_to,
        )
    except ValueError as e:
        # Our own ValueError (e.g. "not translatable")
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        status, error_type, message = map_exception(e)
        raise HTTPException(status, detail={"error": error_type, "message": message})

    return result


# ---------------------------------------------------------------------------
# API: Export transcript
# ---------------------------------------------------------------------------
@app.post("/api/export")
async def export_transcript(body: ExportRequest, request: Request):
    """Fetch and export transcript in the requested format."""
    client_ip = _get_client_ip(request)
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, detail="Rate limit exceeded. Please wait a minute.")

    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    try:
        result = transcript_service.fetch_transcript(
            video_id,
            language=body.language,
            translate_to=body.translate_to,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        status, error_type, message = map_exception(e)
        raise HTTPException(status, detail={"error": error_type, "message": message})

    segments = result["segments"]
    fmt = body.format.lower().strip()

    content_type_map = {
        "txt": "text/plain",
        "srt": "text/plain",
        "vtt": "text/vtt",
        "json": "application/json",
        "md": "text/markdown",
    }
    ext_map = {
        "txt": "txt",
        "srt": "srt",
        "vtt": "vtt",
        "json": "json",
        "md": "md",
    }

    if fmt == "txt":
        content = export_txt(segments, include_timestamps=body.include_timestamps)
    elif fmt == "srt":
        content = export_srt(segments)
    elif fmt == "vtt":
        content = export_vtt(segments)
    elif fmt == "json":
        content = export_json(result)
    elif fmt == "md":
        content = export_markdown(
            segments,
            video_id=video_id,
            language=result.get("language", ""),
            include_timestamps=body.include_timestamps,
        )
    else:
        raise HTTPException(400, detail=f"Unsupported format: {fmt!r}. Use txt, srt, vtt, json, or md.")

    filename = f"transcript_{video_id}.{ext_map.get(fmt, 'txt')}"
    return PlainTextResponse(
        content=content,
        media_type=content_type_map.get(fmt, "text/plain"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Serve static frontend
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"

# Mount static assets (CSS, JS, etc.)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page frontend."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=500)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))
