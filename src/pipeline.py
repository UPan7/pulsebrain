"""Shared pipeline: content -> summary -> categorize -> save -> notify."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.categorize import categorize_content
from src.config import logger
from src.extractors.web import extract_web_article
from src.extractors.youtube import get_transcript, get_video_metadata
from src.router import SourceType, extract_video_id
from src.storage import is_processed, make_content_id, mark_processed, save_entry
from src.summarize import summarize_content

logger = logging.getLogger(__name__)


def process_youtube_video(
    url: str,
    category: str | None = None,
) -> dict[str, Any] | None:
    """Full pipeline for a YouTube video URL.

    Returns dict with entry info on success, None on failure.
    """
    video_id = extract_video_id(url)
    if not video_id:
        return {"error": "Не удалось извлечь ID видео из ссылки."}

    content_id = make_content_id("youtube_video", video_id)
    if is_processed(content_id):
        return {"error": "Это видео уже обработано."}

    # Get metadata
    meta = get_video_metadata(video_id)
    title = meta["title"] or f"Video {video_id}"
    channel = meta["channel"] or "Unknown"
    date_str = meta["upload_date"]

    # Get transcript
    transcript = get_transcript(video_id)
    if not transcript:
        return {"error": f"Транскрипт недоступен для: {title}"}

    # Summarize
    summary = summarize_content(
        content=transcript,
        title=title,
        source_name=channel,
        source_type="youtube_video",
        category=category or "auto-detect",
        date=date_str,
    )
    if not summary:
        return {"error": f"Не удалось создать саммари для: {title}"}

    # Determine category
    is_new_category = False
    final_category = category or summary.get("suggested_category")
    if not final_category:
        final_category, is_new_category = categorize_content(title, transcript)

    # Save
    file_path = save_entry(
        title=title,
        source_url=url,
        source_type="youtube_video",
        source_name=channel,
        date_str=date_str,
        category=final_category,
        relevance=summary.get("relevance_score", 5),
        topics=summary.get("topics", []),
        summary_bullets=summary.get("summary_bullets", []),
        detailed_notes=summary.get("detailed_notes", ""),
        key_insights=summary.get("key_insights", []),
        action_items=summary.get("action_items", []),
    )

    mark_processed(content_id, status="ok")

    result = {
        "title": title,
        "channel": channel,
        "date": date_str,
        "category": final_category,
        "relevance": summary.get("relevance_score", 5),
        "topics": summary.get("topics", []),
        "summary_bullets": summary.get("summary_bullets", []),
        "file_path": str(file_path),
        "source_url": url,
        "source_type": "youtube_video",
    }
    if is_new_category:
        result["is_new_category"] = True
    return result


def process_web_article(
    url: str,
    category: str | None = None,
) -> dict[str, Any] | None:
    """Full pipeline for a web article URL.

    Returns dict with entry info on success, None on failure.
    """
    content_id = make_content_id("web_article", url)
    if is_processed(content_id):
        return {"error": "Эта статья уже обработана."}

    # Extract article
    article = extract_web_article(url)
    if not article:
        return {
            "error": "Не удалось извлечь контент с этой страницы.\n"
            "Возможно, сайт требует JavaScript или блокирует парсинг."
        }

    title = article["title"] or url
    author = article["author"]
    date_str = article["date"]
    sitename = article["sitename"] or ""
    source_name = sitename or url.split("/")[2] if "/" in url else url

    # Summarize
    summary = summarize_content(
        content=article["text"],
        title=title,
        source_name=source_name,
        source_type="web_article",
        category=category or "auto-detect",
        date=date_str,
    )
    if not summary:
        return {"error": f"Не удалось создать саммари для: {title}"}

    # Determine category
    is_new_category = False
    final_category = category or summary.get("suggested_category")
    if not final_category:
        final_category, is_new_category = categorize_content(title, article["text"])

    # Save
    file_path = save_entry(
        title=title,
        source_url=url,
        source_type="web_article",
        source_name=source_name,
        date_str=date_str,
        category=final_category,
        relevance=summary.get("relevance_score", 5),
        topics=summary.get("topics", []),
        summary_bullets=summary.get("summary_bullets", []),
        detailed_notes=summary.get("detailed_notes", ""),
        key_insights=summary.get("key_insights", []),
        action_items=summary.get("action_items", []),
        author=author,
        sitename=sitename,
    )

    mark_processed(content_id, status="ok")

    result = {
        "title": title,
        "source_name": source_name,
        "author": author,
        "date": date_str,
        "category": final_category,
        "relevance": summary.get("relevance_score", 5),
        "topics": summary.get("topics", []),
        "summary_bullets": summary.get("summary_bullets", []),
        "file_path": str(file_path),
        "source_url": url,
        "source_type": "web_article",
        "sitename": sitename,
    }
    if is_new_category:
        result["is_new_category"] = True
    return result
