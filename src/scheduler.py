"""APScheduler — periodic per-user RSS/channel checks for new videos."""

from __future__ import annotations

import asyncio
import logging

import feedparser

from src.config import (
    CHECK_INTERVAL_MINUTES,
    MIN_RELEVANCE_THRESHOLD,
    TELEGRAM_CHAT_IDS,
    load_channels,
    logger,
)
from src.pending import reject_pending
from src.pipeline import process_youtube_video
from src.profile import get_language
from src.storage import is_processed, make_content_id
from src.strings import t

logger = logging.getLogger(__name__)

# YouTube RSS feed URL template
YT_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def fetch_channel_videos(channel_id: str) -> list[dict[str, str]]:
    """Fetch recent videos from a YouTube channel RSS feed."""
    url = YT_RSS_URL.format(channel_id=channel_id)
    try:
        feed = feedparser.parse(url)
        videos = []
        for entry in feed.entries[:10]:
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


async def run_channel_check(chat_id: int, app=None) -> int:
    """Check all enabled channels for ``chat_id``. Returns count processed.

    If *app* is provided, a Telegram notification with the approve/reject
    keyboard is sent to ``chat_id`` for each successfully-staged video.
    A round-digest message is sent at the end of a run *only* when at
    least one counter (processed / rejected / failed) is non-zero — the
    user explicitly does not want "heartbeat" noise on empty runs.
    """
    channels = load_channels(chat_id)
    total_processed = 0
    total_rejected = 0
    total_failed = 0
    channels_checked = sum(1 for ch in channels if ch.get("enabled", True))

    async def _fetch_one(channel):
        if not channel.get("enabled", True):
            return channel, []
        videos = await asyncio.to_thread(fetch_channel_videos, channel["id"])
        return channel, videos

    results = await asyncio.gather(*[_fetch_one(ch) for ch in channels])

    for channel, videos in results:
        category = channel.get("category")

        for video in videos:
            content_id = make_content_id("youtube_video", video["video_id"])
            if is_processed(chat_id, content_id):
                continue

            logger.info("[chat_id=%s] Processing new video: %s", chat_id, video["title"])

            result = await asyncio.to_thread(
                process_youtube_video,
                chat_id,
                video["url"],
                category=category,
                upload_date=video.get("published"),
            )
            if result and "error" not in result:
                threshold = channel.get("min_relevance", MIN_RELEVANCE_THRESHOLD)
                relevance = result.get("relevance", 5)
                if relevance < threshold:
                    logger.info(
                        "[chat_id=%s] Auto-rejected low-relevance: %s (rel=%d, threshold=%d)",
                        chat_id, video["title"], relevance, threshold,
                    )
                    reject_pending(chat_id, result["pending_id"], reason="low_relevance")
                    total_rejected += 1
                    await asyncio.sleep(3)
                    continue

                total_processed += 1
                if result.get("is_new_category"):
                    logger.info(
                        "[chat_id=%s] New category suggested: %s for %s",
                        chat_id, result["category"], video["title"],
                    )
                if app is not None:
                    from src.telegram_bot import send_notification
                    try:
                        await send_notification(app, chat_id, result)
                    except Exception as exc:
                        logger.warning(
                            "[chat_id=%s] Failed to send notification for %s: %s",
                            chat_id, video["title"], exc,
                        )
            elif result and "error" in result:
                total_failed += 1
                logger.warning(
                    "[chat_id=%s] Failed to process %s: %s",
                    chat_id, video["title"], result["error"],
                )

            await asyncio.sleep(3)

    logger.info(
        "[chat_id=%s] Channel check complete. Processed %d, rejected %d, failed %d across %d channels.",
        chat_id, total_processed, total_rejected, total_failed, channels_checked,
    )

    await _send_round_digest(
        app,
        chat_id,
        channels_checked=channels_checked,
        total_processed=total_processed,
        total_rejected=total_rejected,
        total_failed=total_failed,
    )

    return total_processed


async def _send_round_digest(
    app,
    chat_id: int,
    *,
    channels_checked: int,
    total_processed: int,
    total_rejected: int,
    total_failed: int,
) -> None:
    """Post-run summary for ``chat_id``. Sent only on non-zero activity.

    Failures (Telegram down, mock app in tests) are swallowed so the
    scheduler run is never considered broken by a flaky notification.
    """
    if app is None:
        return
    if total_processed == 0 and total_rejected == 0 and total_failed == 0:
        return
    text = t(
        "round_digest_body",
        get_language(chat_id),
        channels=channels_checked,
        processed=total_processed,
        rejected=total_rejected,
        failed=total_failed,
        interval=CHECK_INTERVAL_MINUTES,
    )
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.warning("[chat_id=%s] Failed to send round digest: %s", chat_id, exc)


def setup_scheduler(app):
    """Set up APScheduler: one periodic job iterating over every allowed user.

    Must be called after the Telegram app is initialized.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler()

    async def scheduled_check():
        logger.info("Scheduled channel check starting for %d users...", len(TELEGRAM_CHAT_IDS))
        for chat_id in TELEGRAM_CHAT_IDS:
            try:
                count = await run_channel_check(chat_id, app=app)
                if count > 0:
                    logger.info("[chat_id=%s] Scheduled check found %d new videos", chat_id, count)
            except Exception as exc:
                # One user's failure must not break the others.
                logger.error("[chat_id=%s] Scheduled check failed: %s", chat_id, exc)

    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
        id="channel_check",
        name="Per-user YouTube Channel Check",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured — will check every %d minutes across %d users",
        CHECK_INTERVAL_MINUTES,
        len(TELEGRAM_CHAT_IDS),
    )

    return scheduler
