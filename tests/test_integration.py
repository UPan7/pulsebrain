"""End-to-end integration tests proving the layers compose correctly.

These tests use real storage + categorization + pipeline orchestration.
Only the network boundaries (extractors, LLM) are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir):
    from src.storage import init_processed
    init_processed()


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


def test_youtube_pipeline_end_to_end(tmp_knowledge_dir):
    """YouTube URL → file on disk + processed marker + index + roundtrip parse."""
    import src.config
    from src.pipeline import process_youtube_video
    from src.storage import is_processed, make_content_id, _parse_entry_metadata, search_knowledge

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

    # 1. Result is well-formed
    assert result is not None
    assert "error" not in result
    assert result["title"] == "Claude Code Tutorial"
    assert result["channel"] == "FireshipDev"
    assert result["category"] == "ai-agents"
    assert result["relevance"] == 9

    # 2. File exists at expected path
    file_path = Path(result["file_path"])
    assert file_path.exists()
    assert "/ai-agents/2025/06/" in str(file_path)

    # 3. File contains all five sections
    content = file_path.read_text("utf-8")
    assert "# Claude Code Tutorial" in content
    assert "**Channel:** FireshipDev" in content
    assert "**Category:** ai-agents" in content
    assert "## Summary" in content
    assert "## Detailed Notes" in content
    assert "## Key Insights" in content
    assert "## Action Items" in content
    assert "Bullet one in Russian" in content

    # 4. Marked as processed
    assert is_processed(make_content_id("youtube_video", "intvid01"))

    # 5. Index exists and references the entry
    index = src.config.KNOWLEDGE_DIR / "_index.md"
    assert index.exists()
    assert "Claude Code Tutorial" in index.read_text("utf-8")

    # 6. Metadata roundtrip — saved format is parseable
    info = _parse_entry_metadata(file_path)
    assert info is not None
    assert info["title"] == "Claude Code Tutorial"
    assert info["type"] == "youtube_video"
    assert info["category"] == "ai-agents"

    # 7. Search finds it
    results = search_knowledge("Claude")
    assert any("Claude Code Tutorial" in r["title"] for r in results)


def test_web_pipeline_end_to_end(tmp_knowledge_dir):
    """Web URL → file with author/sitename + processed marker + roundtrip parse."""
    from src.pipeline import process_web_article
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
    assert result["category"] == "n8n-automation"

    # File exists with author + site lines
    path = Path(result["file_path"])
    assert path.exists()
    content = path.read_text("utf-8")
    assert "**Site:** blog.example.com" in content
    assert "**Author:** Alice" in content
    assert "**Type:** web_article" in content

    # Processed marker
    assert is_processed(make_content_id("web_article", "https://blog.example.com/n8n"))

    # Roundtrip
    info = _parse_entry_metadata(path)
    assert info is not None
    assert info["type"] == "web_article"
    assert info["source"] == "blog.example.com"


def test_pipeline_dedup_across_calls(tmp_knowledge_dir):
    """Second call for the same URL is rejected as already-processed."""
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
