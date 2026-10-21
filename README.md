# YouTube Transcriber

A clean web app that extracts **full** YouTube video transcripts. Paste a URL, pick a language, download in 5 formats. No API key needed.

Built with [FastAPI](https://fastapi.tiangolo.com/) + vanilla JS, designed for [Render](https://render.com/) free tier.

## Features

- **Full transcripts** — no word/character cap, handles 3+ hour videos
- **5 export formats** — TXT, SRT, VTT, JSON, Markdown
- **Language support** — auto-detect, manual/generated selection, translation
- **Search & highlight** — live search within the transcript
- **Dark/light mode** — respects system preference, manual toggle
- **Mobile-friendly** — responsive design, touch-accessible
- **Proxy support** — optional rotating proxy for cloud deployments
- **Rate limiting & caching** — protects against abuse, reduces YouTube load

## Local Development

### Prerequisites

- Python 3.10+
- pip

### Setup

```bash
# Clone and enter the directory
cd Transcriber

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install test dependencies
pip install pytest httpx

# Run the server
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

### Run Tests

```bash
pytest tests/ -v
```

## Deploy to Render

### Option A: Blueprint (recommended)

1. Push this repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click **New** → **Blueprint**
4. Connect your GitHub repo
5. Render reads `render.yaml` and creates the service automatically
6. (Optional) Set proxy env vars in the Render dashboard for the service

### Option B: Manual

1. Push this repo to GitHub
2. Go to Render Dashboard → **New** → **Web Service**
3. Connect your GitHub repo
4. Configure:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
   - **Health Check Path**: `/healthz`
5. Add environment variables (see below)
6. Deploy

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | No | `20` | Max requests per IP per minute |
| `CACHE_TTL_SECONDS` | No | `300` | Cache TTL in seconds |
| `CACHE_MAX_SIZE` | No | `100` | Max cached entries |
| `ALLOWED_ORIGINS` | No | _(same-origin)_ | CORS origins (comma-separated) |
| `WEBSHARE_PROXY_USERNAME` | No | — | Webshare proxy username |
| `WEBSHARE_PROXY_PASSWORD` | No | — | Webshare proxy password |
| `WEBSHARE_PROXY_LOCATION` | No | `US` | Webshare proxy location |
| `GENERIC_HTTP_PROXY` | No | — | Generic HTTP proxy URL |
| `GENERIC_HTTPS_PROXY` | No | — | Generic HTTPS proxy URL |

## Troubleshooting

### "YouTube is blocking requests from this server's IP"

**Cause**: YouTube blocks known cloud/datacenter IP ranges (AWS, GCP, Render, etc.).

**Fix**: Configure a rotating residential proxy:
1. Sign up for [Webshare](https://www.webshare.io/) (they have a free tier with 10 proxies)
2. Set `WEBSHARE_PROXY_USERNAME` and `WEBSHARE_PROXY_PASSWORD` in your Render environment variables
3. Redeploy

Alternatively, use any HTTP/HTTPS proxy via `GENERIC_HTTP_PROXY` / `GENERIC_HTTPS_PROXY`.

### First request is very slow (30-60 seconds)

**Cause**: Render free tier spins down instances after ~15 minutes of inactivity (cold start).

**Fix**: This is expected behavior on the free plan. The first request after a cold start wakes the instance. Subsequent requests are fast. To avoid this, upgrade to a paid plan or set up an external health-check ping.

### "No transcripts available for this video"

**Cause**: The video creator has disabled captions, or the video has no auto-generated captions.

**Fix**: Not all videos have transcripts. For videos with no captions, you can use the local-only Whisper fallback (see below).

### "Video is age-restricted"

**Cause**: Age-restricted videos require authentication to access transcripts.

**Fix**: This is a YouTube limitation. The `youtube-transcript-api` library does support cookie-based auth for advanced use cases — see their docs.

## Whisper Fallback (Local Only)

For videos with **no captions** at all, there's a local-only fallback script using [yt-dlp](https://github.com/yt-dlp/yt-dlp) + [OpenAI Whisper](https://github.com/openai/whisper):

```bash
# Install extra dependencies (NOT deployed to Render)
pip install yt-dlp openai-whisper

# Run
python whisper_fallback.py "https://www.youtube.com/watch?v=VIDEO_ID" --model base --output transcript.txt
```

> ⚠️ **Not runnable on Render free tier** — Whisper requires 1GB+ RAM and benefits from a GPU. Use locally only.

## Project Structure

```
Transcriber/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── services/
│   │   ├── __init__.py
│   │   ├── url_parser.py    # YouTube URL → video ID
│   │   ├── transcript.py    # Transcript fetching + caching
│   │   ├── exporters.py     # TXT/SRT/VTT/JSON/MD export
│   │   └── errors.py        # Exception → HTTP error mapping
│   └── static/
│       ├── index.html        # Single-page frontend
│       └── style.css         # Design system
├── tests/
│   ├── test_url_parser.py    # URL parsing tests
│   ├── test_exporters.py     # Export format tests
│   ├── test_errors.py        # Error mapping tests
│   └── test_api.py           # API endpoint tests
├── whisper_fallback.py       # Local-only Whisper fallback
├── requirements.txt          # Pinned Python dependencies
├── render.yaml               # Render Blueprint config
├── .env.example              # Environment variable template
├── .gitignore
└── README.md
```

## License

MIT
