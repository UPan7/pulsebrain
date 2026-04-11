"""YouTube transcript and metadata extraction via yt-dlp + youtube-transcript-api."""

from __future__ import annotations

import logging
import random
import subprocess

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from src.config import PROXY_CREDENTIALS_FILE, TRANSCRIPT_LANGUAGES

logger = logging.getLogger(__name__)

_COOKIES_PATH = "/app/cookies.txt"

_BASE_YTDLP = ["yt-dlp", "--cookies", _COOKIES_PATH]

# ── Proxy helpers ───────────────────────────────────────────────────────────

_proxy_lines: list[str] = []


def _load_proxy_lines() -> list[str]:
    """Load and cache proxy credential lines from file."""
    global _proxy_lines
    if _proxy_lines:
        return _proxy_lines
    try:
        text = PROXY_CREDENTIALS_FILE.read_text(encoding="utf-8").strip()
        _proxy_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    except FileNotFoundError:
        logger.warning("Proxy credentials file not found: %s", PROXY_CREDENTIALS_FILE)
    return _proxy_lines


def _make_proxy_config() -> GenericProxyConfig | None:
    """Build a GenericProxyConfig using a random proxy credential line."""
    lines = _load_proxy_lines()
    if not lines:
        return None
    cred_line = random.choice(lines)  # user:pass@host:port
    proxy_url = f"http://{cred_line}"
    return GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)


# ── Transcript via youtube-transcript-api ───────────────────────────────────


_MAX_RETRIES = 3


def get_transcript(video_id: str, languages: list[str] | None = None) -> str | None:
    """Fetch transcript for a YouTube video via youtube-transcript-api.

    Uses rotating residential proxies with retries on failure.
    """
    if languages is None:
        languages = TRANSCRIPT_LANGUAGES

    for attempt in range(1, _MAX_RETRIES + 1):
        proxy_config = _make_proxy_config()
        api = YouTubeTranscriptApi(proxy_config=proxy_config) if proxy_config else YouTubeTranscriptApi()
        try:
            transcript = api.fetch(video_id, languages=languages)
            text = " ".join(snippet.text for snippet in transcript)
            return text if text.strip() else None
        except Exception as exc:
            logger.debug("Transcript attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, video_id, exc)
            if attempt == _MAX_RETRIES:
                logger.warning("No transcript available for %s after %d attempts: %s", video_id, _MAX_RETRIES, exc)
                return None


def get_video_metadata(video_id: str) -> dict[str, str | None]:
    """Fetch video title, channel name, and upload date via yt-dlp."""
    try:
        result = subprocess.run(
            [
                *_BASE_YTDLP,
                "--skip-download",
                "--no-check-formats",
                "--ignore-no-formats-error",
                "--print", "%(title)s",
                "--print", "%(channel)s",
                "--print", "%(upload_date)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 3 and lines[0] not in ("", "NA"):
            upload_date = lines[2]
            if len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            return {
                "title": lines[0],
                "channel": lines[1],
                "upload_date": upload_date,
            }
    except Exception as exc:
        logger.warning("Failed to get metadata for %s: %s", video_id, exc)

    return {"title": None, "channel": None, "upload_date": None}


def resolve_channel_id(url: str) -> tuple[str | None, str | None]:
    """Resolve a YouTube channel URL to (channel_id, channel_name) via yt-dlp."""
    try:
        result = subprocess.run(
            [
                *_BASE_YTDLP,
                "--skip-download",
                "--print", "%(channel_id)s",
                "--print", "%(channel)s",
                "--playlist-items", "1",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2 and lines[0] not in ("", "NA"):
            return lines[0], lines[1]
    except Exception as exc:
        logger.warning("Failed to resolve channel %s: %s", url, exc)

    return None, None


def get_recent_video_ids(channel_id: str, count: int = 3) -> list[str]:
    """Get the most recent video IDs from a channel."""
    try:
        result = subprocess.run(
            [
                *_BASE_YTDLP,
                "--skip-download",
                "--print", "%(id)s",
                "--playlist-items", f"1:{count}",
                f"https://www.youtube.com/channel/{channel_id}/videos",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        ids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return ids
    except Exception as exc:
        logger.warning("Failed to get recent videos for %s: %s", channel_id, exc)
        return []
