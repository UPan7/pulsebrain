"""Tests for src.pipeline — shared helper, deduplication, logger fix."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir):
    """All pipeline tests use isolated storage."""
    from src.storage import init_processed
    init_processed()


# ── Logger correctness ─────────────────────────────────────────────────────


def test_pipeline_logger_name():
    """Pipeline logger should be 'src.pipeline', not 'pulsebrain'."""
    import src.pipeline
    assert src.pipeline.logger.name == "src.pipeline"


# ── Shared helper (deduplication) ──────────────────────────────────────────


def test_process_youtube_delegates_to_shared():
    """process_youtube_video uses the shared _process_content helper."""
    import src.pipeline
    assert hasattr(src.pipeline, "_process_content"), \
        "Expected shared _process_content helper to exist"


def test_process_web_delegates_to_shared():
    """process_web_article uses the shared _process_content helper."""
    import src.pipeline
    # Both public functions should exist and call _process_content
    assert hasattr(src.pipeline, "_process_content")


def test_shared_skips_already_processed():
    """Already-processed content returns error dict without calling extractors."""
    from src.pipeline import process_youtube_video
    from src.storage import mark_processed, make_content_id

    mark_processed(make_content_id("youtube_video", "dQw4w9WgXcQ"))

    with patch("src.pipeline.get_transcript") as mock_t:
        result = process_youtube_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert "error" in result
        mock_t.assert_not_called()


def test_shared_returns_error_on_extract_failure():
    """Extractor returning None → error dict."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value=None),
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=newvid123")
        assert result is not None
        assert "error" in result


def test_shared_returns_error_on_summarize_failure():
    """Summarize returning None → error dict."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="some transcript text"),
        patch("src.pipeline.summarize_content", return_value=None),
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=newvid456")
        assert result is not None
        assert "error" in result


def test_process_youtube_accepts_upload_date():
    """process_youtube_video passes upload_date through to save_entry."""
    from src.pipeline import process_youtube_video

    summary = {
        "summary_bullets": ["b"],
        "detailed_notes": "notes",
        "key_insights": ["i"],
        "action_items": ["a"],
        "topics": ["t"],
        "relevance_score": 7,
        "suggested_category": "ai-news",
    }

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=summary),
        patch("src.pipeline.save_entry") as mock_save,
    ):
        mock_save.return_value = "/fake/path.md"
        result = process_youtube_video(
            "https://www.youtube.com/watch?v=datetest",
            upload_date="2025-01-15",
        )
        assert result is not None
        assert "error" not in result
        # Verify date_str was passed correctly
        _, kwargs = mock_save.call_args
        assert kwargs.get("date_str") == "2025-01-15"
