"""Tests for src.scheduler — parallel RSS, date passthrough."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir):
    """All scheduler tests use isolated storage."""
    from src.storage import init_processed
    init_processed()


def _make_channels(count: int = 3):
    return [
        {"name": f"Channel{i}", "id": f"UC{i:024d}", "category": "ai-news", "enabled": True}
        for i in range(count)
    ]


def _make_video(video_id: str, published: str = "2025-06-15T10:00:00"):
    return {
        "video_id": video_id,
        "title": f"Video {video_id}",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "published": published,
    }


# ── Parallel RSS fetches ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parallel_rss_fetch():
    """3 channels with 0.3s fetch each → total < 1s (parallel, not 0.9s+)."""
    from src.scheduler import run_channel_check

    channels = _make_channels(3)

    def slow_fetch(channel_id):
        time.sleep(0.5)
        return []  # No new videos

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", side_effect=slow_fetch),
    ):
        start = time.monotonic()
        await run_channel_check()
        elapsed = time.monotonic() - start

    # Sequential would be ~1.5s; parallel should be ~0.5s
    assert elapsed < 1.0, f"Expected parallel fetch < 1s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_skips_disabled_channels():
    """Disabled channels are not fetched."""
    from src.scheduler import run_channel_check

    channels = [
        {"name": "Active", "id": "UC_active", "category": "ai-news", "enabled": True},
        {"name": "Disabled", "id": "UC_disabled", "category": "ai-news", "enabled": False},
    ]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=[]) as mock_fetch,
    ):
        await run_channel_check()
        # Only called for active channel
        assert mock_fetch.call_count == 1
        mock_fetch.assert_called_with("UC_active")


@pytest.mark.asyncio
async def test_skips_already_processed():
    """Already-processed videos are not re-processed."""
    from src.scheduler import run_channel_check
    from src.storage import mark_processed, make_content_id

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("old_vid"), _make_video("new_vid")]

    # Mark one as already processed
    mark_processed(make_content_id("youtube_video", "old_vid"))

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"title": "T"}) as mock_proc,
    ):
        await run_channel_check()
        # Only the new video should be processed
        assert mock_proc.call_count == 1


@pytest.mark.asyncio
async def test_passes_publish_date():
    """RSS published date is forwarded as upload_date."""
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("vid1", published="2025-03-20T12:00:00")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"title": "T"}) as mock_proc,
    ):
        await run_channel_check()
        mock_proc.assert_called_once()
        _, kwargs = mock_proc.call_args
        assert kwargs.get("upload_date") == "2025-03-20T12:00:00"
