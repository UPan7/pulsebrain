"""YouTube transcript and metadata extraction via proxied HTTP + youtube-transcript-api."""

from __future__ import annotations

import logging
import random
import re
import time

import feedparser
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from src.config import PROXY_CREDENTIALS_FILE, TRANSCRIPT_LANGUAGES

logger = logging.getLogger(__name__)

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


def _get_random_proxy_dict() -> dict[str, str] | None:
    """Return a requests-compatible proxy dict with a random credential."""
    lines = _load_proxy_lines()
    if not lines:
        return None
    cred_line = random.choice(lines)
    proxy_url = f"http://{cred_line}"
    return {"http": proxy_url, "https": proxy_url}


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
            # Exponential backoff: 1s, 2s
            time.sleep(2 ** (attempt - 1))


def get_video_metadata(video_id: str) -> dict[str, str | None]:
    """Fetch video title, channel name, and upload date via oEmbed API."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "title": data.get("title"),
                "channel": data.get("author_name"),
                "upload_date": None,
            }
    except Exception as exc:
        logger.warning("Failed to get metadata for %s: %s", video_id, exc)

    return {"title": None, "channel": None, "upload_date": None}


def resolve_channel_id(url: str) -> tuple[str | None, str | None]:
    """Resolve a YouTube channel URL to (channel_id, channel_name) via page scraping."""
    # Normalize: add @ if missing for handle-style URLs
    normalized = url.rstrip("/")
    if re.search(r"youtube\.com/[^@/]+$", normalized):
        handle = normalized.rsplit("/", 1)[-1]
        normalized = f"https://www.youtube.com/@{handle}"

    proxies = _get_random_proxy_dict()
    try:
        resp = requests.get(
            normalized,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            proxies=proxies,
            timeout=15,
        )
        html = resp.text

        # Extract channel ID from meta tag or canonical link
        cid_match = re.search(r'"externalId"\s*:\s*"(UC[\w-]+)"', html)
        if not cid_match:
            cid_match = re.search(r'channel_id=(UC[\w-]+)', html)
        if not cid_match:
            cid_match = re.search(r'"channelId"\s*:\s*"(UC[\w-]+)"', html)

        # Extract channel name
        name_match = re.search(r'"author"\s*:\s*"([^"]+)"', html)
        if not name_match:
            name_match = re.search(r'<title>([^<]+)</title>', html)

        if cid_match:
            channel_id = cid_match.group(1)
            channel_name = name_match.group(1).replace(" - YouTube", "").strip() if name_match else None
            return channel_id, channel_name
    except Exception as exc:
        logger.warning("Failed to resolve channel %s: %s", url, exc)

    return None, None


def get_recent_video_ids(channel_id: str, count: int = 3) -> list[str]:
    """Get the most recent video IDs from a channel via RSS feed."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(url)
        ids = []
        for entry in feed.entries[:count]:
            vid = entry.get("yt_videoid", "")
            if vid:
                ids.append(vid)
        return ids
    except Exception as exc:
        logger.warning("Failed to get recent videos for %s: %s", channel_id, exc)
        return []
