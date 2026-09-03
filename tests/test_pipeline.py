"""Tests for src.pipeline — per-user shared helper, deduplication, logger."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_knowledge_dir, chat_id):
    """All pipeline tests use isolated per-user storage."""
    from src.config import ensure_user_dirs
    from src.storage import init_processed

    ensure_user_dirs(chat_id)
    init_processed(chat_id)


# ── Logger correctness ─────────────────────────────────────────────────────


def test_pipeline_logger_name():
    import src.pipeline
    assert src.pipeline.logger.name == "src.pipeline"


# ── Shared helper (deduplication) ──────────────────────────────────────────


def test_process_youtube_delegates_to_shared():
    import src.pipeline
    assert hasattr(src.pipeline, "_process_content")


def test_process_web_delegates_to_shared():
    import src.pipeline
    assert hasattr(src.pipeline, "_process_content")


def test_shared_skips_already_processed(chat_id):
    from src.pipeline import process_youtube_video
    from src.storage import mark_processed, make_content_id

    mark_processed(chat_id, make_content_id("youtube_video", "dQw4w9WgXcQ"))

    with patch("src.pipeline.get_transcript") as mock_t:
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert "error" in result
        mock_t.assert_not_called()


def test_shared_returns_error_on_extract_failure(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value=None),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=newvid123")
        assert result is not None
        assert "error" in result


def test_shared_returns_error_on_summarize_failure(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="some transcript text"),
        patch("src.pipeline.summarize_content", return_value=None),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=newvid456")
        assert result is not None
        assert "error" in result


def test_process_youtube_accepts_upload_date(chat_id):
    from src.pipeline import process_youtube_video

    summary = {
        "summary_bullets": ["b"],
        "detailed_notes": "notes",
        "key_insights": ["i"],
        "action_items": ["a"],
        "topics": ["t"],
        "relevance_score": 7,
    }

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=summary),
        patch("src.pipeline.categorize_content", return_value=("ai-news", False)),
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        result = process_youtube_video(
            chat_id,
            "https://www.youtube.com/watch?v=datetest",
            upload_date="2025-01-15",
        )
        assert result is not None
        assert "error" not in result
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


def test_process_web_article_happy_path(chat_id):
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.categorize_content", return_value=("ai-news", False)),
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        result = process_web_article(chat_id, "https://example.com/foo")

    assert result is not None
    assert "error" not in result
    assert result["title"] == "Article Title"
    assert result["sitename"] == "example.com"
    assert result["author"] == "Jane Doe"
    assert result["source_type"] == "web_article"
    assert result["category"] == "ai-news"


def test_process_web_article_already_processed(chat_id):
    from src.pipeline import process_web_article
    from src.storage import mark_processed, make_content_id

    mark_processed(chat_id, make_content_id("web_article", "https://example.com/dup"))

    with patch("src.pipeline.extract_web_article") as mock_extract:
        result = process_web_article(chat_id, "https://example.com/dup")
        assert "error" in result
        mock_extract.assert_not_called()


def test_process_web_article_extract_failure(chat_id):
    from src.pipeline import process_web_article

    with patch("src.pipeline.extract_web_article", return_value=None):
        result = process_web_article(chat_id, "https://example.com/bad")

    assert result is not None
    assert "error" in result


def test_process_web_article_summarize_failure(chat_id):
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=None),
    ):
        result = process_web_article(chat_id, "https://example.com/foo")

    assert "error" in result


def test_process_web_article_propagates_author_and_sitename(chat_id):
    from src.pipeline import process_web_article

    with (
        patch("src.pipeline.extract_web_article", return_value=_article_dict()),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.categorize_content", return_value=("ai-news", False)),
        patch("src.pipeline.stage_pending") as mock_save,
    ):
        mock_save.return_value = "abc12345"
        process_web_article(chat_id, "https://example.com/foo")

    _, kwargs = mock_save.call_args
    assert kwargs["author"] == "Jane Doe"
    assert kwargs["sitename"] == "example.com"


def test_process_content_unknown_source_type(chat_id):
    from src.pipeline import _process_content

    result = _process_content(chat_id, "https://x", "podcast")
    assert "error" in result
    assert "podcast" in result["error"]


def test_pipeline_always_calls_categorize_when_no_user_category(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
        patch("src.pipeline.categorize_content", return_value=("computed-cat", False)) as mock_cat,
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=catfb01")

    mock_cat.assert_called_once()
    assert result["category"] == "computed-cat"


def test_pipeline_skips_categorize_when_user_specified_category(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
        patch("src.pipeline.categorize_content") as mock_cat,
    ):
        result = process_youtube_video(
            chat_id,
            "https://www.youtube.com/watch?v=usercat1",
            category="wordpress",
        )

    mock_cat.assert_not_called()
    assert result["category"] == "wordpress"
    assert result.get("is_new_category") is not True


def test_pipeline_returns_is_new_category_flag(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="abc12345"),
        patch("src.pipeline.categorize_content", return_value=("new-cat", True)),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=newcat01")

    assert result.get("is_new_category") is True


def test_pipeline_marks_processed_pending_after_stage(chat_id):
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
        process_youtube_video(chat_id, "https://www.youtube.com/watch?v=marked01")

    cid = make_content_id("youtube_video", "marked01")
    assert is_processed(chat_id, cid)
    assert src.storage._processed_caches[chat_id][cid]["status"] == "pending"


def test_pipeline_result_has_pending_id_not_file_path(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="deadbeef"),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=pendid01")

    assert result["pending_id"] == "deadbeef"
    assert "file_path" not in result


def test_pipeline_passes_raw_transcript_to_stage_pending(chat_id):
    from src.pipeline import process_youtube_video

    transcript = "Full transcript body that must reach the pending registry."
    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value=transcript),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="deadbeef") as mock_stage,
    ):
        process_youtube_video(chat_id, "https://www.youtube.com/watch?v=rawtxt01")

    assert mock_stage.call_args.kwargs["raw_text"] == transcript


def test_pipeline_passes_article_text_to_stage_pending(chat_id):
    from src.pipeline import process_web_article

    article = {**_article_dict(), "text": "The full body of the article."}
    with (
        patch("src.pipeline.extract_web_article", return_value=article),
        patch("src.pipeline.summarize_content", return_value=_summary_dict()),
        patch("src.pipeline.stage_pending", return_value="cafef00d") as mock_stage,
    ):
        process_web_article(chat_id, "https://example.com/foo")

    assert mock_stage.call_args.kwargs["raw_text"] == "The full body of the article."


def test_pipeline_invalid_video_url_returns_error(chat_id):
    """URL with no extractable video ID → error dict."""
    from src.pipeline import process_youtube_video

    result = process_youtube_video(chat_id, "https://www.youtube.com/watch")
    assert "error" in result


# ── Machine-readable error contract ────────────────────────────────────────


def _transcript_failing(kind: str, code: str):
    """Fake get_transcript that fails and fills the caller's failure sink."""

    def _fake(video_id, languages=None, *, failure_out=None):
        if failure_out is not None:
            failure_out.update(kind=kind, code=code)
        return None

    return _fake


def test_error_carries_stable_error_code(chat_id):
    """Callers branch on the t() key, never on the localized prose."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value=None),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=codetest")

    assert result["error_code"] == "pipeline_err_transcript_unavailable"
    assert result["error"] != result["error_code"]


def test_transcript_permanent_propagates_kind(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", new=_transcript_failing("permanent", "TranscriptsDisabled")),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=permvid1")

    assert result["failure_kind"] == "permanent"
    assert result["failure_detail"] == "TranscriptsDisabled"


def test_transcript_transient_propagates_kind(chat_id):
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", new=_transcript_failing("transient", "ProxyError")),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=transvid")

    assert result["failure_kind"] == "transient"
    assert result["failure_detail"] == "ProxyError"


def test_transcript_failure_defaults_transient(chat_id):
    """A plain return_value=None patch leaves the sink empty — must not blacklist."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value=None),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=defvid01")

    assert result["failure_kind"] == "transient"
    assert "failure_detail" not in result


def test_summarize_failure_is_transient(chat_id):
    """An OpenRouter blip must not permanently blacklist the video."""
    from src.pipeline import process_youtube_video

    with (
        patch("src.pipeline.get_video_metadata", return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript"),
        patch("src.pipeline.summarize_content", return_value=None),
    ):
        result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=sumfail1")

    assert result["failure_kind"] == "transient"
    assert result["error_code"] == "pipeline_err_summarize_failed"


def test_already_processed_is_duplicate_kind(chat_id):
    from src.pipeline import process_youtube_video
    from src.storage import make_content_id, mark_processed

    mark_processed(chat_id, make_content_id("youtube_video", "dupvid01"))

    result = process_youtube_video(chat_id, "https://www.youtube.com/watch?v=dupvid01")
    assert result["failure_kind"] == "duplicate"
    assert result["error_code"] == "pipeline_err_video_already_processed"


def test_web_already_processed_is_duplicate_kind(chat_id):
    from src.pipeline import process_web_article
    from src.storage import make_content_id, mark_processed

    url = "https://example.com/dup"
    mark_processed(chat_id, make_content_id("web_article", url))

    result = process_web_article(chat_id, url)
    assert result["failure_kind"] == "duplicate"


def test_video_id_extract_failure_is_permanent(chat_id):
    """A malformed URL will not parse tomorrow either."""
    from src.pipeline import process_youtube_video

    result = process_youtube_video(chat_id, "https://www.youtube.com/watch")
    assert result["failure_kind"] == "permanent"
    assert result["error_code"] == "pipeline_err_video_id_extract"


def test_unknown_source_type_is_permanent(chat_id):
    """A routing bug, not an outage."""
    from src.pipeline import _process_content

    result = _process_content(chat_id, "https://x.com/a", "podcast")
    assert result["failure_kind"] == "permanent"
    assert result["error_code"] == "pipeline_err_unknown_source_type"


def test_web_extract_failure_propagates_kind(chat_id):
    from src.pipeline import process_web_article

    def _fake(url, *, failure_out=None):
        if failure_out is not None:
            failure_out.update(kind="permanent", code="TextTooShort")
        return None

    with patch("src.pipeline.extract_web_article", new=_fake):
        result = process_web_article(chat_id, "https://example.com/paywall")

    assert result["failure_kind"] == "permanent"
    assert result["failure_detail"] == "TextTooShort"


def test_web_extract_failure_defaults_transient(chat_id):
    from src.pipeline import process_web_article

    with patch("src.pipeline.extract_web_article", return_value=None):
        result = process_web_article(chat_id, "https://example.com/dead")

    assert result["failure_kind"] == "transient"
