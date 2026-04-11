"""Tests for src.router — URL detection edge cases."""

from __future__ import annotations

from src.router import SourceType, detect_source_type, extract_video_id


# ── detect_source_type ─────────────────────────────────────────────────────


def test_detect_youtube_video_standard():
    assert detect_source_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == SourceType.YOUTUBE_VIDEO


def test_detect_youtube_video_short():
    assert detect_source_type("https://youtu.be/dQw4w9WgXcQ") == SourceType.YOUTUBE_VIDEO


def test_detect_youtube_video_with_timestamp():
    assert detect_source_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120") == SourceType.YOUTUBE_VIDEO


def test_detect_youtube_video_with_playlist():
    assert detect_source_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx") == SourceType.YOUTUBE_VIDEO


def test_detect_youtube_channel_handle():
    assert detect_source_type("https://youtube.com/@fireship") == SourceType.YOUTUBE_CHANNEL


def test_detect_youtube_channel_id():
    assert detect_source_type("https://youtube.com/channel/UCsBjURrPoezykLs9EqgamOA") == SourceType.YOUTUBE_CHANNEL


def test_detect_youtube_channel_legacy():
    assert detect_source_type("https://youtube.com/c/Fireship") == SourceType.YOUTUBE_CHANNEL


def test_detect_web_article():
    assert detect_source_type("https://example.com/article") == SourceType.WEB_ARTICLE


def test_detect_empty_string():
    """Empty string falls through to WEB_ARTICLE."""
    assert detect_source_type("") == SourceType.WEB_ARTICLE


# ── extract_video_id ───────────────────────────────────────────────────────


def test_extract_video_id_standard():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_short():
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_with_extra_params():
    assert extract_video_id("https://www.youtube.com/watch?v=abc123&list=PLxxx") == "abc123"


def test_extract_video_id_no_v_param():
    assert extract_video_id("https://youtube.com/watch") is None


def test_extract_video_id_non_youtube():
    assert extract_video_id("https://example.com") is None


def test_extract_video_id_empty():
    assert extract_video_id("") is None
