"""End-to-end integration tests proving the layers compose correctly.

These tests use real storage + categorization + pipeline + pending registry.
Only the network boundaries (extractors, LLM) are mocked.

The flow is now: pipeline stages → user approves → commit_pending writes
the file. We verify both phases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir):
    from src.pending import init_pending
    from src.storage import init_processed
    init_processed()
    init_pending()


def _summary():
    return {
        "summary_bullets": ["Bullet one in Russian", "Bullet two"],
        "detailed_notes": "Detailed notes paragraph in Russian.",
        "key_insights": ["Insight one"],
        "action_items": ["Action one"],
        "topics": ["ai-agents", "claude"],
        "relevance_score": 9,
        "suggested_category": "ai-agents",
    }


def test_youtube_pipeline_stage_then_commit(tmp_knowledge_dir):
    """YouTube URL → stage (no file) → commit → file + index + roundtrip."""
    import src.config
    from src.pipeline import process_youtube_video
    from src.pending import commit_pending, get_pending
    from src.storage import (
        is_processed, make_content_id, _parse_entry_metadata, search_knowledge,
    )

    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "Claude Code Tutorial", "channel": "FireshipDev", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value="A long transcript about Claude Code."),
        patch("src.pipeline.summarize_content", return_value=_summary()),
    ):
        result = process_youtube_video(
            "https://www.youtube.com/watch?v=intvid01",
            upload_date="2025-06-15",
        )

    # 1. Result is well-formed and points at a pending entry, NOT a file
    assert "error" not in result
    assert result["title"] == "Claude Code Tutorial"
    assert result["channel"] == "FireshipDev"
    assert result["category"] == "ai-agents"
    assert "pending_id" in result
    assert "file_path" not in result

    # 2. No .md file exists yet
    md_files = list(src.config.KNOWLEDGE_DIR.rglob("*.md"))
    assert md_files == []

    # 3. content_id is marked processed (status pending) so scheduler skips it
    cid = make_content_id("youtube_video", "intvid01")
    assert is_processed(cid)

    # 4. Pending entry can be looked up
    entry = get_pending(result["pending_id"])
    assert entry is not None
    assert entry["title"] == "Claude Code Tutorial"

    # 5. User approves → file appears, index regenerates, parse roundtrip works
    file_path = commit_pending(result["pending_id"])
    assert file_path is not None
    assert file_path.exists()
    assert "/ai-agents/2025/06/" in str(file_path)

    content = file_path.read_text("utf-8")
    assert "# Claude Code Tutorial" in content
    assert "**Channel:** FireshipDev" in content
    assert "**Category:** ai-agents" in content
    for section in ("## Summary", "## Detailed Notes", "## Key Insights", "## Action Items"):
        assert section in content

    # 6. Pending entry is dropped
    assert get_pending(result["pending_id"]) is None

    # 7. Index updated
    index = src.config.KNOWLEDGE_DIR / "_index.md"
    assert index.exists()
    assert "Claude Code Tutorial" in index.read_text("utf-8")

    # 8. Metadata roundtrip
    info = _parse_entry_metadata(file_path)
    assert info is not None
    assert info["type"] == "youtube_video"
    assert info["category"] == "ai-agents"

    # 9. Search finds it
    assert any("Claude Code Tutorial" in r["title"] for r in search_knowledge("Claude"))


def test_web_pipeline_stage_then_commit(tmp_knowledge_dir):
    """Web URL → stage → commit → file with author/sitename, processed marker."""
    import src.config
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
    summary = _summary()
    summary["suggested_category"] = "n8n-automation"

    with (
        patch("src.pipeline.extract_web_article", return_value=article),
        patch("src.pipeline.summarize_content", return_value=summary),
    ):
        result = process_web_article("https://blog.example.com/n8n")

    assert result["title"] == "How To Self-Host N8N"
    assert result["sitename"] == "blog.example.com"
    assert result["author"] == "Alice"
    assert "pending_id" in result

    # No file yet
    assert list(src.config.KNOWLEDGE_DIR.rglob("*.md")) == []

    # Commit
    file_path = commit_pending(result["pending_id"])
    assert file_path is not None
    assert file_path.exists()

    content = file_path.read_text("utf-8")
    assert "**Site:** blog.example.com" in content
    assert "**Author:** Alice" in content
    assert "**Type:** web_article" in content

    cid = make_content_id("web_article", "https://blog.example.com/n8n")
    assert is_processed(cid)

    info = _parse_entry_metadata(file_path)
    assert info is not None
    assert info["type"] == "web_article"
    assert info["source"] == "blog.example.com"


def test_youtube_pipeline_stage_then_reject(tmp_knowledge_dir):
    """Reject path: stage → reject → no file, but content_id stays processed."""
    import src.config
    from src.pipeline import process_youtube_video
    from src.pending import reject_pending, get_pending
    from src.storage import is_processed, make_content_id

    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "Spam", "channel": "X", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value="some text"),
        patch("src.pipeline.summarize_content", return_value=_summary()),
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=rejvid01")

    pending_id = result["pending_id"]
    assert reject_pending(pending_id) is True

    # No file exists
    assert list(src.config.KNOWLEDGE_DIR.rglob("*.md")) == []

    # Pending entry is gone
    assert get_pending(pending_id) is None

    # content_id is still flagged as processed (status="rejected")
    cid = make_content_id("youtube_video", "rejvid01")
    assert is_processed(cid)

    # Re-processing the same URL is rejected as already-processed
    with (
        patch("src.pipeline.get_video_metadata") as mock_meta,
        patch("src.pipeline.get_transcript") as mock_t,
        patch("src.pipeline.summarize_content") as mock_s,
    ):
        again = process_youtube_video("https://www.youtube.com/watch?v=rejvid01")
        assert "error" in again
        assert "уже обработано" in again["error"]
        mock_meta.assert_not_called()
        mock_t.assert_not_called()
        mock_s.assert_not_called()


def test_pipeline_dedup_across_calls_after_stage(tmp_knowledge_dir):
    """Second call for the same URL is rejected even before approval."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={
            "title": "T", "channel": "C", "upload_date": None,
        }),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary()),
    ):
        first = process_youtube_video("https://www.youtube.com/watch?v=dupvid01")
        second = process_youtube_video("https://www.youtube.com/watch?v=dupvid01")

    assert "error" not in first
    assert "error" in second
    assert "уже обработано" in second["error"]
