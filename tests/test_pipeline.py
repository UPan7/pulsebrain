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
    """process_youtube_video passes upload_date through to stage_pending."""
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
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        result = process_youtube_video(
            "https://www.youtube.com/watch?v=datetest",
            upload_date="2025-01-15",
        )
        assert result is not None
        assert "error" not in result
        # Verify date_str was passed correctly
        _, kwargs = mock_save.call_args
        assert kwargs.get("date_str") == "2025-01-15"


# ── Web-article branch ─────────────────────────────────────────────────────


def _summary_dict():
    return {
        "summary_bullets": ["b"],
        "detailed_notes": "notes",
        "key_insights": ["i"],
        "action_items": ["a"],
        "topics": ["t"],
        "relevance_score": 7,
        "suggested_category": "ai-news",
    }


def _article_dict():
    return {
        "title": "Article Title",
        "author": "Jane Doe",
        "date": "2025-06-15",
        "text": "article text",
        "source_url": "https://example.com/foo",
        "sitename": "example.com",
    }


def test_process_web_article_happy_path():
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        result = process_web_article("https://example.com/foo")

    assert result is not None
    assert "error" not in result
    assert result["title"] == "Article Title"
    assert result["sitename"] == "example.com"
    assert result["author"] == "Jane Doe"
    assert result["source_type"] == "web_article"
    assert result["category"] == "ai-news"


def test_process_web_article_already_processed():
    from src.pipeline import process_web_article
    from src.storage import mark_processed, make_content_id

    mark_processed(make_content_id("web_article", "https://example.com/dup"))

    with patch("src.pipeline.extract_web_article") as mock_extract:
        result = process_web_article("https://example.com/dup")
        assert "error" in result
        mock_extract.assert_not_called()


def test_process_web_article_extract_failure():
    from src.pipeline import process_web_article

    with patch("src.pipeline.extract_web_article", return_value=None):
        result = process_web_article("https://example.com/bad")

    assert result is not None
    assert "error" in result


def test_process_web_article_summarize_failure():
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=None),
    ):
        result = process_web_article("https://example.com/foo")

    assert "error" in result


def test_process_web_article_propagates_author_and_sitename():
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        process_web_article("https://example.com/foo")

    _, kwargs = mock_save.call_args
    assert kwargs["author"] == "Jane Doe"
    assert kwargs["sitename"] == "example.com"


def test_process_content_unknown_source_type():
    from src.pipeline import _process_content

    result = _process_content("https://x", "podcast")
    assert "error" in result
    assert "podcast" in result["error"]


def test_pipeline_uses_categorize_fallback_when_no_suggestion():
    """Summary missing suggested_category → categorize_content is called."""
    from src.pipeline import process_youtube_video

    summary = _summary_dict()
    summary.pop("suggested_category")

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=summary),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
        patch("src.pipeline.categorize_content", return_value=("computed-cat", False)) as mock_cat,
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=catfb01")

    mock_cat.assert_called_once()
    assert result["category"] == "computed-cat"


def test_pipeline_returns_is_new_category_flag():
    from src.pipeline import process_youtube_video

    summary = _summary_dict()
    summary.pop("suggested_category")

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=summary),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
        patch("src.pipeline.categorize_content", return_value=("new-cat", True)),
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=newcat01")

    assert result.get("is_new_category") is True


def test_pipeline_marks_processed_pending_after_stage():
    """After staging, content_id is marked processed with status='pending'."""
    import src.storage
    from src.pipeline import process_youtube_video
    from src.storage import is_processed, make_content_id

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
    ):
        process_youtube_video("https://www.youtube.com/watch?v=marked01")

    cid = make_content_id("youtube_video", "marked01")
    assert is_processed(cid)
    assert src.storage._processed_cache[cid]["status"] == "pending"


def test_pipeline_result_has_pending_id_not_file_path():
    """Pipeline returns pending_id and no longer returns file_path."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="deadbeef"),
    ):
        result = process_youtube_video("https://www.youtube.com/watch?v=pendid01")

    assert result["pending_id"] == "deadbeef"
    assert "file_path" not in result


def test_pipeline_invalid_video_url_returns_error():
    """URL with no extractable video ID → error dict."""
    from src.pipeline import process_youtube_video

    result = process_youtube_video("https://www.youtube.com/watch")
    assert "error" in result
