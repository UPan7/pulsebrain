"""YouTube transcript and metadata extraction via yt-dlp."""

from __future__ import annotations

import glob as glob_module
import logging
import os
import re
import subprocess
import tempfile

from src.config import TRANSCRIPT_LANGUAGES

logger = logging.getLogger(__name__)

_COOKIES_PATH = "/app/cookies.txt"

_BASE_YTDLP = ["yt-dlp", "--cookies", _COOKIES_PATH]


def _parse_vtt(filepath: str) -> str | None:
    """Parse a VTT subtitle file and return deduplicated plain text."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    text_lines = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE") or "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            text_lines.append(line)

    # Deduplicate consecutive identical lines (VTT repeats overlap lines)
    deduped: list[str] = []
    for line in text_lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return " ".join(deduped) if deduped else None


def get_transcript(video_id: str, languages: list[str] | None = None) -> str | None:
    """Fetch transcript for a YouTube video via yt-dlp.

    Tries manual subtitles first, then auto-generated.
    Returns plain text with timestamps stripped.
    """
    if languages is None:
        languages = TRANSCRIPT_LANGUAGES

    url = f"https://www.youtube.com/watch?v={video_id}"
    lang_str = ",".join(languages)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_tmpl = os.path.join(tmpdir, "%(id)s")
        for sub_flags in [["--write-subs"], ["--write-auto-subs"]]:
            cmd = [
                *_BASE_YTDLP,
                "--skip-download",
                "--no-check-formats",
                "--ignore-errors",
                "--ignore-no-formats-error",
                *sub_flags,
                "--sub-langs", lang_str,
                "--sub-format", "vtt",
                "-o", out_tmpl,
                url,
            ]
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                files = glob_module.glob(os.path.join(tmpdir, "*.vtt"))
                if files:
                    text = _parse_vtt(files[0])
                    if text:
                        return text
            except Exception as exc:
                logger.debug("yt-dlp sub attempt failed for %s: %s", video_id, exc)

    logger.warning("No transcript available for %s", video_id)
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
