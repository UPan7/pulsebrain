"""End-to-end integration tests proving the layers compose correctly.

These tests use real per-user storage + categorization + pipeline + pending
registry. Only the network boundaries (extractors, LLM) are mocked.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs
    from src.pending import init_pending
    from src.storage import init_processed

    ensure_user_dirs(chat_id)
    init_processed(chat_id)
    init_pending(chat_id)


def _summary():
    return {
        "summary_bullets": ["Bullet one in Russian", "Bullet two"],
        "detailed_notes": "Detailed notes paragraph in Russian.",
        "key_insights": ["Insight one"],
        "action_items": ["Action one"],
        "topics": ["ai-agents", "claude"],
        "relevance_score": 9,
    }


def test_youtube_pipeline_stage_then_commit(tmp_knowledge_dir, chat_id):
    """YouTube URL → stage (no file) → commit → file + index + roundtrip."""
    from src.config import user_knowledge_dir
    from src.pipeline import process_youtube_video
    from src.pending import commit_pending, get_pending
    from src.storage import (
        is_processed, make_content_id, _parse_entry_metadata, search_knowledge,
        _source_sibling_path,
    )

    transcript = "A long transcript about Claude Code that must survive end-to-end."
    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "Claude Code Tutorial", "channel": "FireshipDev", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value=transcript),
        patch("src.pipeline.summarize_content", return_value=_summary()),
        patch("src.pipeline.categorize_content", return_value=("ai-agents", False)),
    ):
        result = process_youtube_video(
            chat_id,
            "https://www.youtube.com/watch?v=intvid01",
            upload_date="2025-06-15",
        )

    assert "error" not in result
    assert result["title"] == "Claude Code Tutorial"
    assert result["channel"] == "FireshipDev"
    assert result["category"] == "ai-agents"
    assert "pending_id" in result
    assert "file_path" not in result

    root = user_knowledge_dir(chat_id)
    md_files = list(root.rglob("*.md"))
    assert md_files == []

    cid = make_content_id("youtube_video", "intvid01")
    assert is_processed(chat_id, cid)

    entry = get_pending(chat_id, result["pending_id"])
    assert entry is not None
    assert entry["title"] == "Claude Code Tutorial"

    file_path = commit_pending(chat_id, result["pending_id"])
    assert file_path is not None
    assert file_path.exists()
    # Cross-platform path check
    parts = file_path.parts
    assert "ai-agents" in parts
    assert "2025" in parts
    assert "06" in parts

    content = file_path.read_text("utf-8")
    assert "# Claude Code Tutorial" in content
    assert "**Channel:** FireshipDev" in content
    assert "**Category:** ai-agents" in content
    for section in ("## Summary", "## Detailed Notes", "## Key Insights", "## Action Items"):
        assert section in content

    assert get_pending(chat_id, result["pending_id"]) is None

    index = root / "_index.md"
    assert index.exists()
    assert "Claude Code Tutorial" in index.read_text("utf-8")

    info = _parse_entry_metadata(chat_id, file_path)
    assert info is not None
    assert info["type"] == "youtube_video"
    assert info["category"] == "ai-agents"

    assert any("Claude Code Tutorial" in r["title"] for r in search_knowledge(chat_id, "Claude"))

    sibling = _source_sibling_path(file_path)
    assert sibling.exists()
    assert sibling.read_text("utf-8") == transcript


def test_web_pipeline_stage_then_commit(tmp_knowledge_dir, chat_id):
    """Web URL → stage → commit → file with author/sitename, processed marker."""
    from src.config import user_knowledge_dir
    from src.pipeline import process_web_article
    from src.pending import commit_pending
    from src.storage import is_processed, make_content_id, _parse_entry_metadata

    article = {
        "title": "How To Self-Host N8N",
        "author": "Alice",
        "date": "2025-06-15",
        "text": "Long article about hosting n8n on Hetzner.",
        "source_url": "https://blog.example.com/n8n",
        "sitename": "blog.example.com",
    }
    with (
        patch("src.pipeline.extract_web_article", return_value=article),
        patch("src.pipeline.summarize_content", return_value=_summary()),
        patch("src.pipeline.categorize_content", return_value=("n8n-automation", False)),
    ):
        result = process_web_article(chat_id, "https://blog.example.com/n8n")

    assert result["title"] == "How To Self-Host N8N"
    assert result["sitename"] == "blog.example.com"
    assert result["author"] == "Alice"
    assert "pending_id" in result

    root = user_knowledge_dir(chat_id)
    assert list(root.rglob("*.md")) == []

    file_path = commit_pending(chat_id, result["pending_id"])
    assert file_path is not None
    assert file_path.exists()

    content = file_path.read_text("utf-8")
    assert "**Site:** blog.example.com" in content
    assert "**Author:** Alice" in content
    assert "**Type:** web_article" in content

    cid = make_content_id("web_article", "https://blog.example.com/n8n")
    assert is_processed(chat_id, cid)

    info = _parse_entry_metadata(chat_id, file_path)
    assert info is not None
    assert info["type"] == "web_article"
    assert info["source"] == "blog.example.com"


def test_youtube_pipeline_stage_then_reject(tmp_knowledge_dir, chat_id):
    """Reject path: stage → reject → no file, but content_id stays processed."""
    from src.config import user_knowledge_dir
    from src.pipeline import process_youtube_video
    from src.pending import reject_pending, get_pending
    from src.storage import is_processed, make_content_id

    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "Spam", "channel": "X", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value="some text"),
        patch("src.pipeline.summarize_content", return_value=_summary()),
        patch("src.pipeline.categorize_content", return_value=("ai-agents", False)),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=rejvid01")

    pending_id = result["pending_id"]
    assert reject_pending(chat_id, pending_id) is True

    root = user_knowledge_dir(chat_id)
    assert list(root.rglob("*.md")) == []

    assert get_pending(chat_id, pending_id) is None

    cid = make_content_id("youtube_video", "rejvid01")
    assert is_processed(chat_id, cid)

    with (
        patch("src.pipeline.get_video_metadata") as mock_meta,
        patch("src.pipeline.get_transcript") as mock_t,
        patch("src.pipeline.summarize_content") as mock_s,
    ):
        again = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=rejvid01")
        assert "error" in again
        assert "already been processed" in again["error"]
        mock_meta.assert_not_called()
        mock_t.assert_not_called()
        mock_s.assert_not_called()


def test_pipeline_dedup_across_calls_after_stage(tmp_knowledge_dir, chat_id):
    """Second call for the same URL is rejected even before approval."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "T", "channel": "C", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary()),
        patch("src.pipeline.categorize_content", return_value=("ai-agents", False)),
    ):
        first = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=dupvid01")
        second = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=dupvid01")

    assert "error" not in first
    assert "error" in second
    assert "already been processed" in second["error"]
