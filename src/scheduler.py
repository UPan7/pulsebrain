"""APScheduler — periodic RSS/channel checks for new videos."""

from __future__ import annotations

import asyncio
import logging

import feedparser

from src.config import CHECK_INTERVAL_MINUTES, load_channels, logger
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


async def run_channel_check() -> int:
    """Check all enabled channels for new videos. Returns count of processed videos."""
    channels = load_channels()
    total_processed = 0

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
        channel_name = channel["name"]

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
                total_processed += 1
                if result.get("is_new_category"):
                    logger.info("New category suggested: %s for %s", result["category"], video["title"])
            elif result and "error" in result:
                logger.warning(
                    "Failed to process %s: %s", video["title"], result["error"]
                )

            # Rate limiting: 3-second delay between YouTube requests
            await asyncio.sleep(3)

    logger.info("Channel check complete. Processed %d new videos.", total_processed)
    return total_processed


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
            count = await run_channel_check()
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
