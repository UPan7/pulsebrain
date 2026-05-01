"""Tests for src.scheduler — per-user parallel RSS, date passthrough, gate."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir, chat_id):
    """All scheduler tests use isolated per-user storage."""
    from src.config import ensure_user_dirs
    from src.storage import init_processed

    ensure_user_dirs(chat_id)
    init_processed(chat_id)


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
async def test_parallel_rss_fetch(chat_id):
    from src.scheduler import run_channel_check

    channels = _make_channels(3)

    def slow_fetch(channel_id):
        time.sleep(0.5)
        return []

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", side_effect=slow_fetch),
    ):
        start = time.monotonic()
        await run_channel_check(chat_id)
        elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"Expected parallel fetch < 1s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_skips_disabled_channels(chat_id):
    from src.scheduler import run_channel_check

    channels = [
        {"name": "Active", "id": "UC_active", "category": "ai-news", "enabled": True},
        {"name": "Disabled", "id": "UC_disabled", "category": "ai-news", "enabled": False},
    ]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=[]) as mock_fetch,
    ):
        await run_channel_check(chat_id)
        assert mock_fetch.call_count == 1
        mock_fetch.assert_called_with("UC_active")


@pytest.mark.asyncio
async def test_skips_already_processed(chat_id):
    from src.scheduler import run_channel_check
    from src.storage import mark_processed, make_content_id

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("old_vid"), _make_video("new_vid")]

    mark_processed(chat_id, make_content_id("youtube_video", "old_vid"))

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"title": "T"}) as mock_proc,
    ):
        await run_channel_check(chat_id)
        assert mock_proc.call_count == 1


@pytest.mark.asyncio
async def test_passes_publish_date(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("vid1", published="2025-03-20T12:00:00")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"title": "T"}) as mock_proc,
    ):
        await run_channel_check(chat_id)
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
async def test_run_channel_check_logs_error_dict_results(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", return_value={"error": "no transcript"}),
    ):
        count = await run_channel_check(chat_id)

    assert count == 0


@pytest.mark.asyncio
async def test_run_channel_check_sleeps_between_videos(chat_id):
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
        await run_channel_check(chat_id)

    assert sleep_calls == [3, 3]


@pytest.mark.asyncio
async def test_run_channel_check_handles_new_category_log(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": None, "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "is_new_category": True, "category": "robotics"}),
    ):
        count = await run_channel_check(chat_id)

    assert count == 1


# ── Notifications ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_channel_check_sends_notification_when_app_provided(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1"), _make_video("v2")]
    fake_app = MagicMock()

    sent = []

    async def fake_notify(app, cid, result):
        sent.append((cid, result))

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "deadbeef"}),
        patch("src.telegram_bot.send_notification", side_effect=fake_notify),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=fake_app)

    assert count == 2
    assert len(sent) == 2
    assert all(cid == chat_id for cid, _ in sent)


@pytest.mark.asyncio
async def test_run_channel_check_swallows_notification_errors(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    fake_app = MagicMock()

    async def fail_notify(*args, **kwargs):
        raise RuntimeError("telegram down")

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "x"}),
        patch("src.telegram_bot.send_notification", side_effect=fail_notify),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=fake_app)

    assert count == 1


@pytest.mark.asyncio
async def test_run_channel_check_skips_notification_when_no_app(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "x"}),
        patch("src.telegram_bot.send_notification") as mock_notify,
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id)

    mock_notify.assert_not_called()


# ── Relevance gate ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_channel_check_auto_rejects_below_global_threshold(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    fake_app = MagicMock()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "Meh", "pending_id": "dead", "relevance": 3}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 7),
        patch("src.scheduler.reject_pending", return_value=True) as mock_reject,
        patch("src.telegram_bot.send_notification") as mock_notify,
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=fake_app)

    assert count == 0
    mock_reject.assert_called_once_with(chat_id, "dead", reason="low_relevance")
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_run_channel_check_uses_per_channel_threshold(chat_id):
    from src.scheduler import run_channel_check

    channels = [{
        "name": "Strict", "id": "UC_strict", "category": "ai-news",
        "enabled": True, "min_relevance": 9,
    }]
    videos = [_make_video("v1")]
    fake_app = MagicMock()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "dead", "relevance": 7}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 4),
        patch("src.scheduler.reject_pending", return_value=True) as mock_reject,
        patch("src.telegram_bot.send_notification") as mock_notify,
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=fake_app)

    assert count == 0
    mock_reject.assert_called_once_with(chat_id, "dead", reason="low_relevance")
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_run_channel_check_passes_when_above_threshold(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    fake_app = MagicMock()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "live", "relevance": 8}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 4),
        patch("src.scheduler.reject_pending") as mock_reject,
        patch("src.telegram_bot.send_notification", new_callable=AsyncMock) as mock_notify,
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=fake_app)

    assert count == 1
    mock_reject.assert_not_called()
    mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_run_channel_check_relevance_gate_waits_rate_limit(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1"), _make_video("v2")]

    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "d", "relevance": 2}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 5),
        patch("src.scheduler.reject_pending", return_value=True),
        patch("src.scheduler.asyncio.sleep", side_effect=fake_sleep),
    ):
        await run_channel_check(chat_id)

    assert sleep_calls == [3, 3]


def test_setup_scheduler_uses_check_interval(allowlist_env):
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


# ── Round digest ────────────────────────────────────────────────────────


def _fake_app_with_bot():
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_round_digest_silent_on_empty_run(chat_id):
    from src.scheduler import run_channel_check

    channels = [
        {"name": "A", "id": "UC_a", "category": "ai-news", "enabled": True},
        {"name": "B", "id": "UC_b", "category": "ai-news", "enabled": True},
    ]
    app = _fake_app_with_bot()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=[]),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id, app=app)

    app.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_round_digest_sent_when_only_rejected(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    app = _fake_app_with_bot()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "Meh", "pending_id": "dead", "relevance": 2}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 5),
        patch("src.scheduler.reject_pending", return_value=True),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id, app=app)

    app.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_round_digest_sent_when_only_failed(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    app = _fake_app_with_bot()

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"error": "no transcript"}),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id, app=app)

    app.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_round_digest_counts_mixed_outcomes(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("pass"), _make_video("reject"), _make_video("fail")]
    app = _fake_app_with_bot()

    def fake_process(cid, url, **kwargs):
        if "pass" in url:
            return {"title": "Pass", "pending_id": "p1", "relevance": 9}
        if "reject" in url:
            return {"title": "Reject", "pending_id": "p2", "relevance": 2}
        return {"error": "no transcript"}

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video", side_effect=fake_process),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 5),
        patch("src.scheduler.reject_pending", return_value=True),
        patch("src.telegram_bot.send_notification", new_callable=AsyncMock),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id, app=app)

    app.bot.send_message.assert_called_once()
    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Channels checked: 1" in text
    assert "New in /pending: 1" in text
    assert "Auto-rejected: 1" in text
    assert "Errors: 1" in text


@pytest.mark.asyncio
async def test_round_digest_not_sent_when_app_is_none(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=[]),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id)

    assert count == 0


@pytest.mark.asyncio
async def test_round_digest_swallows_send_failures(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"error": "no transcript"}),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        count = await run_channel_check(chat_id, app=app)

    assert count == 0
    app.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_round_digest_counts_only_enabled_channels(chat_id):
    from src.scheduler import run_channel_check

    channels = [
        {"name": "A", "id": "UC_a", "category": "ai-news", "enabled": True},
        {"name": "B", "id": "UC_b", "category": "ai-news", "enabled": False},
        {"name": "C", "id": "UC_c", "category": "ai-news", "enabled": True},
    ]
    videos = [_make_video("v1")]
    app = _fake_app_with_bot()

    def fake_fetch(channel_id):
        return videos if channel_id == "UC_a" else []

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", side_effect=fake_fetch),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "T", "pending_id": "x", "relevance": 9}),
        patch("src.telegram_bot.send_notification", new_callable=AsyncMock),
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id, app=app)

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Channels checked: 2" in text


@pytest.mark.asyncio
async def test_scheduler_reject_passes_low_relevance_reason(chat_id):
    from src.scheduler import run_channel_check

    channels = [{"name": "Ch", "id": "UC_ch", "category": "ai-news", "enabled": True}]
    videos = [_make_video("v1")]

    with (
        patch("src.scheduler.load_channels", return_value=channels),
        patch("src.scheduler.fetch_channel_videos", return_value=videos),
        patch("src.scheduler.process_youtube_video",
              return_value={"title": "Meh", "pending_id": "x", "relevance": 2}),
        patch("src.scheduler.MIN_RELEVANCE_THRESHOLD", 5),
        patch("src.scheduler.reject_pending", return_value=True) as mock_reject,
        patch("src.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        await run_channel_check(chat_id)

    mock_reject.assert_called_once_with(chat_id, "x", reason="low_relevance")
