"""Shared pipeline: content -> summary -> categorize -> save -> notify."""

from __future__ import annotations

import logging
from typing import Any

from src.categorize import categorize_content
from src.extractors.web import extract_web_article
from src.extractors.youtube import get_transcript, get_video_metadata
from src.pending import stage_pending
from src.router import extract_video_id
from src.storage import is_processed, make_content_id, mark_processed
from src.summarize import summarize_content

logger = logging.getLogger(__name__)


def _process_content(
    url: str,
    source_type: str,
    category: str | None = None,
    upload_date: str | None = None,
) -> dict[str, Any] | None:
    """Shared pipeline for any content type.

    Returns dict with entry info on success, or dict with 'error' key on failure.
    """
    # ── Extract ─────────────────────────────────────────────────────────────
    if source_type == "youtube_video":
        video_id = extract_video_id(url)
        if not video_id:
            return {"error": "Не удалось извлечь ID видео из ссылки."}

        content_id = make_content_id("youtube_video", video_id)
        if is_processed(content_id):
            return {"error": "Это видео уже обработано."}

        meta = get_video_metadata(video_id)
        title = meta["title"] or f"Video {video_id}"
        source_name = meta["channel"] or "Unknown"
        date_str = upload_date or meta["upload_date"]

        content = get_transcript(video_id)
        if not content:
            return {"error": f"Транскрипт недоступен для: {title}"}

    elif source_type == "web_article":
        content_id = make_content_id("web_article", url)
        if is_processed(content_id):
            return {"error": "Эта статья уже обработана."}

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
        content = article["text"]
    else:
        return {"error": f"Неизвестный тип контента: {source_type}"}

    # ── Summarize ───────────────────────────────────────────────────────────
    summary = summarize_content(
        content=content,
        title=title,
        source_name=source_name,
        source_type=source_type,
        date=date_str,
    )
    if not summary:
        return {"error": f"Не удалось создать саммари для: {title}"}

    # ── Categorize ──────────────────────────────────────────────────────────
    # User-supplied category wins; otherwise run the dynamic categorizer.
    # We intentionally do NOT read any "suggested_category" from the summary
    # dict — summarize_content no longer infers categories (see its docstring).
    if category:
        final_category, is_new_category = category, False
    else:
        final_category, is_new_category = categorize_content(title, content)

    # ── Stage (awaiting user approval) ──────────────────────────────────────
    # raw_text is the lossless original — saved alongside the .md on commit
    # so the knowledge base can be used as a corpus for future tools/queries.
    stage_kwargs: dict[str, Any] = {
        "content_id": content_id,
        "source_url": url,
        "source_type": source_type,
        "source_name": source_name,
        "title": title,
        "date_str": date_str,
        "category": final_category,
        "is_new_category": is_new_category,
        "relevance": summary.get("relevance_score", 5),
        "topics": summary.get("topics", []),
        "summary_bullets": summary.get("summary_bullets", []),
        "detailed_notes": summary.get("detailed_notes", ""),
        "key_insights": summary.get("key_insights", []),
        "action_items": summary.get("action_items", []),
        "author": locals().get("author") if source_type == "web_article" else None,
        "sitename": locals().get("sitename") if source_type == "web_article" else None,
        "raw_text": content,
    }

    pending_id = stage_pending(**stage_kwargs)
    mark_processed(content_id, status="pending")

    # ── Build result ────────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "title": title,
        "date": date_str,
        "category": final_category,
        "relevance": summary.get("relevance_score", 5),
        "topics": summary.get("topics", []),
        "summary_bullets": summary.get("summary_bullets", []),
        "pending_id": pending_id,
        "source_url": url,
        "source_type": source_type,
    }
    if source_type == "youtube_video":
        result["channel"] = source_name
    else:
        result["source_name"] = source_name
        result["author"] = locals().get("author")
        result["sitename"] = locals().get("sitename")

    if is_new_category:
        result["is_new_category"] = True
    return result


def process_youtube_video(
    url: str,
    category: str | None = None,
    upload_date: str | None = None,
) -> dict[str, Any] | None:
    """Full pipeline for a YouTube video URL."""
    return _process_content(url, "youtube_video", category=category, upload_date=upload_date)


def process_web_article(
    url: str,
    category: str | None = None,
) -> dict[str, Any] | None:
    """Full pipeline for a web article URL."""
    return _process_content(url, "web_article", category=category)
