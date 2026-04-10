"""URL type detection and routing."""

from __future__ import annotations

from urllib.parse import urlparse


class SourceType:
    YOUTUBE_VIDEO = "youtube_video"
    YOUTUBE_CHANNEL = "youtube_channel"
    WEB_ARTICLE = "web_article"


def detect_source_type(url: str) -> str:
    """Determine the type of content a URL points to."""
    url_lower = url.lower()

    # YouTube video
    if "youtube.com/watch" in url_lower or "youtu.be/" in url_lower:
        return SourceType.YOUTUBE_VIDEO

    # YouTube channel / handle
    if (
        "youtube.com/@" in url_lower
        or "youtube.com/channel/" in url_lower
        or "youtube.com/c/" in url_lower
    ):
        return SourceType.YOUTUBE_CHANNEL

    # Everything else = web article
    return SourceType.WEB_ARTICLE


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    parsed = urlparse(url)

    if "youtu.be" in (parsed.hostname or ""):
        # https://youtu.be/VIDEO_ID
        return parsed.path.lstrip("/").split("/")[0] or None

    if "youtube.com" in (parsed.hostname or ""):
        from urllib.parse import parse_qs

        qs = parse_qs(parsed.query)
        video_ids = qs.get("v")
        if video_ids:
            return video_ids[0]

    return None
