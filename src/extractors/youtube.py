"""YouTube transcript extraction via youtube-transcript-api."""

from __future__ import annotations

import logging
import subprocess

from youtube_transcript_api import YouTubeTranscriptApi

from src.config import TRANSCRIPT_LANGUAGES

logger = logging.getLogger(__name__)


def get_transcript(video_id: str, languages: list[str] | None = None) -> str | None:
    """Fetch transcript for a YouTube video.

    Priority: manual subs in preferred languages -> auto-generated -> None.
    Returns plain text with timestamps stripped.
    """
    if languages is None:
        languages = TRANSCRIPT_LANGUAGES

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try manual subtitles first
        for lang in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                return " ".join(entry["text"] for entry in transcript.fetch())
            except Exception:
                continue

        # Fall back to auto-generated
        for lang in languages:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                return " ".join(entry["text"] for entry in transcript.fetch())
            except Exception:
                continue

        return None
    except Exception as exc:
        logger.warning("Failed to get transcript for %s: %s", video_id, exc)
        return None


def get_video_metadata(video_id: str) -> dict[str, str | None]:
    """Fetch video title, channel name, and upload date via yt-dlp."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
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
        if len(lines) >= 3:
            upload_date = lines[2]
            # Format YYYYMMDD -> YYYY-MM-DD
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
                "yt-dlp",
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
        if len(lines) >= 2 and lines[0] != "NA":
            return lines[0], lines[1]
    except Exception as exc:
        logger.warning("Failed to resolve channel %s: %s", url, exc)

    return None, None


def get_recent_video_ids(channel_id: str, count: int = 3) -> list[str]:
    """Get the most recent video IDs from a channel."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
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
