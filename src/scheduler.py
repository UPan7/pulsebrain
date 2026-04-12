"""APScheduler — periodic RSS/channel checks for new videos."""

from __future__ import annotations

import asyncio
import logging

import feedparser

from src.config import (
    CHECK_INTERVAL_MINUTES,
    MIN_RELEVANCE_THRESHOLD,
    TELEGRAM_CHAT_ID,
    load_channels,
    logger,
)
from src.pending import reject_pending
from src.pipeline import process_youtube_video
from src.storage import is_processed, make_content_id

logger = logging.getLogger(__name__)

# YouTube RSS feed URL template
YT_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def fetch_channel_videos(channel_id: str) -> list[dict[str, str]]:
    """Fetch recent videos from a YouTube channel RSS feed."""
    url = YT_RSS_URL.format(channel_id=channel_id)
    try:
        feed = feedparser.parse(url)
        videos = []
        for entry in feed.entries[:10]:  # Last 10 entries
            video_id = entry.get("yt_videoid", "")
            if not video_id and "watch?v=" in entry.get("link", ""):
                video_id = entry["link"].split("watch?v=")[1].split("&")[0]
            if video_id:
                videos.append({
                    "video_id": video_id,
                    "title": entry.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published": entry.get("published", ""),
                })
        return videos
    except Exception as exc:
        logger.error("Failed to fetch RSS for channel %s: %s", channel_id, exc)
        return []


async def run_channel_check(app=None) -> int:
    """Check all enabled channels for new videos. Returns count of processed videos.

    If *app* is provided, a Telegram notification with the approve/reject
    keyboard is sent for each successfully-staged video so the user can
    review the auto-fetched content before it lands in the knowledge base.
    A round-digest message is always sent at the end of a run (even when
    zero videos passed the filter) so the user can tell "nothing happened"
    apart from "bot is dead".
    """
    channels = load_channels()
    total_processed = 0
    total_rejected = 0
    total_failed = 0
    channels_checked = sum(1 for ch in channels if ch.get("enabled", True))

    # Phase 1: Parallel RSS fetches (I/O-bound, safe to parallelize)
    async def _fetch_one(channel):
        if not channel.get("enabled", True):
            return channel, []
        videos = await asyncio.to_thread(fetch_channel_videos, channel["id"])
        return channel, videos

    results = await asyncio.gather(*[_fetch_one(ch) for ch in channels])

    # Phase 2: Sequential video processing (respects rate limits)
    for channel, videos in results:
        category = channel.get("category")

        for video in videos:
            content_id = make_content_id("youtube_video", video["video_id"])
            if is_processed(content_id):
                continue

            logger.info("Processing new video: %s", video["title"])

            result = await asyncio.to_thread(
                process_youtube_video,
                video["url"],
                category=category,
                upload_date=video.get("published"),
            )
            if result and "error" not in result:
                # Relevance gate: per-channel override > global default.
                # Below threshold → silent reject, no notification, no
                # processed-counter bump. The content_id is already
                # marked pending inside the pipeline; reject_pending
                # flips it to "rejected" so the scheduler never
                # re-fetches it. The rejection is logged to
                # rejected_log.jsonl so the user can inspect it via
                # /rejected.
                threshold = channel.get("min_relevance", MIN_RELEVANCE_THRESHOLD)
                relevance = result.get("relevance", 5)
                if relevance < threshold:
                    logger.info(
                        "Auto-rejected low-relevance video: %s (rel=%d, threshold=%d)",
                        video["title"], relevance, threshold,
                    )
                    reject_pending(result["pending_id"], reason="low_relevance")
                    total_rejected += 1
                    await asyncio.sleep(3)
                    continue

                total_processed += 1
                if result.get("is_new_category"):
                    logger.info("New category suggested: %s for %s", result["category"], video["title"])
                if app is not None:
                    # Lazy import to avoid a circular import at module load
                    from src.telegram_bot import send_notification
                    try:
                        await send_notification(app, result)
                    except Exception as exc:
                        logger.warning("Failed to send notification for %s: %s",
                                       video["title"], exc)
            elif result and "error" in result:
                total_failed += 1
                logger.warning(
                    "Failed to process %s: %s", video["title"], result["error"]
                )

            # Rate limiting: 3-second delay between YouTube requests
            await asyncio.sleep(3)

    logger.info(
        "Channel check complete. Processed %d, rejected %d, failed %d across %d channels.",
        total_processed, total_rejected, total_failed, channels_checked,
    )

    await _send_round_digest(
        app,
        channels_checked=channels_checked,
        total_processed=total_processed,
        total_rejected=total_rejected,
        total_failed=total_failed,
    )

    return total_processed


async def _send_round_digest(
    app,
    *,
    channels_checked: int,
    total_processed: int,
    total_rejected: int,
    total_failed: int,
) -> None:
    """Post-run summary. Always sent when *app* is provided, even for
    zero-result runs — the whole point is to prove to the user that
    the scheduler is alive.

    Failures (Telegram down, mock app in tests) are swallowed so the
    scheduler run is never considered broken by a flaky notification.
    """
    if app is None:
        return
    text = (
        "🔄 Прогон завершён\n\n"
        f"Каналов проверено: {channels_checked}\n"
        f"Новых в /pending: {total_processed}\n"
        f"Авто-отклонено: {total_rejected}\n"
        f"Ошибок: {total_failed}\n\n"
        f"Следующий через {CHECK_INTERVAL_MINUTES} мин"
    )
    try:
        await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as exc:
        logger.warning("Failed to send round digest: %s", exc)


def setup_scheduler(app) -> None:
    """Set up APScheduler to run channel checks periodically.

    Must be called after the Telegram app is initialized.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler()

    async def scheduled_check():
        logger.info("Scheduled channel check starting...")
        try:
            count = await run_channel_check(app=app)
            if count > 0:
                logger.info("Scheduled check found %d new videos", count)
        except Exception as exc:
            logger.error("Scheduled check failed: %s", exc)

    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
        id="channel_check",
        name="YouTube Channel Check",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured — will check every %d minutes", CHECK_INTERVAL_MINUTES
    )

    return scheduler
