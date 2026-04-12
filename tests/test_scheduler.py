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


# ── fetch_channel_videos ────────────────────────────────────────────────


def test_fetch_channel_videos_parses_yt_videoid():
    from src.scheduler import fetch_channel_videos

    fake_feed = MagicMock()
    fake_feed.entries = [
        {"yt_videoid": "abc", "title": "T1", "link": "https://yt/watch?v=abc",
         "published": "2025-06-01"},
    ]
    with patch("src.scheduler.feedparser.parse", return_value=fake_feed):
        videos = fetch_channel_videos("UC1")

    assert len(videos) == 1
    assert videos[0]["video_id"] == "abc"
    assert videos[0]["title"] == "T1"
    assert videos[0]["published"] == "2025-06-01"


def test_fetch_channel_videos_falls_back_to_link_parsing():
    """Entry without yt_videoid uses link?v= parsing."""
    from src.scheduler import fetch_channel_videos

    fake_feed = MagicMock()
    fake_feed.entries = [
        {"yt_videoid": "", "title": "T", "link": "https://www.youtube.com/watch?v=fromlink&t=10",
         "published": ""},
    ]
    with patch("src.scheduler.feedparser.parse", return_value=fake_feed):
        videos = fetch_channel_videos("UC1")

    assert len(videos) == 1
    assert videos[0]["video_id"] == "fromlink"


def test_fetch_channel_videos_handles_exception():
    from src.scheduler import fetch_channel_videos

    with patch("src.scheduler.feedparser.parse", side_effect=Exception("rss")):
        assert fetch_channel_videos("UC1") == []


def test_fetch_channel_videos_skips_entries_without_id():
    from src.scheduler import fetch_channel_videos

    fake_feed = MagicMock()
    fake_feed.entries = [
        {"yt_videoid": "ok", "title": "OK", "link": "", "published": ""},
        {"yt_videoid": "", "title": "Skip", "link": "https://example.com/no-vid", "published": ""},
    ]
    with patch("src.scheduler.feedparser.parse", return_value=fake_feed):
        videos = fetch_channel_videos("UC1")

    assert len(videos) == 1
    assert videos[0]["video_id"] == "ok"


# ── run_channel_check extras ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_channel_check_logs_error_dict_results():
    """Error-dict result does not bump the processed counter."""
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"error": "no transcript"}),
    ):
        count = await run_channel_check()

    assert count == 0


@pytest.mark.asyncio
async def test_run_channel_check_sleeps_between_videos():
    """Each processed video is followed by a 3s rate-limit sleep."""
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1"), _make_video("v2")]

    sleep_calls = []
    real_sleep = asyncio.sleep

    async def fake_sleep(secs):
        sleep_calls.append(secs)
        await real_sleep(0)

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"title": "T"}),
        patch("src.scheduler.asyncio.sleep", side_effect=fake_sleep),
    ):
        await run_channel_check()

    assert sleep_calls == [3, 3]


@pytest.mark.asyncio
async def test_run_channel_check_handles_new_category_log():
    """Result with is_new_category triggers the info-log branch (no crash)."""
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": None, "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "is_new_category": True, "category": "robotics"}),
    ):
        count = await run_channel_check()

    assert count == 1


# ── setup_scheduler ─────────────────────────────────────────────────────


def test_setup_scheduler_uses_check_interval():
    from src.scheduler import setup_scheduler

    fake_scheduler = MagicMock()
    with (
        patch("apscheduler.schedulers.asyncio.AsyncIOScheduler", return_value=fake_scheduler),
        patch("src.scheduler.CHECK_INTERVAL_MINUTES", 17),
    ):
        result = setup_scheduler(MagicMock())

    assert result is fake_scheduler
    fake_scheduler.add_job.assert_called_once()
    _, kwargs = fake_scheduler.add_job.call_args
    assert kwargs["id"] == "channel_check"
    assert kwargs["replace_existing"] is True
