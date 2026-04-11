"""Tests for src.extractors.youtube — retry backoff, metadata."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_transcript_succeeds_first_try():
    """Transcript returned on first attempt — no retries."""
    from src.extractors.youtube import get_transcript

    mock_snippet = MagicMock()
    mock_snippet.text = "hello world"
    mock_transcript = [mock_snippet]

    with patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi:
        instance = MockApi.return_value
        instance.fetch.return_value = mock_transcript

        result = get_transcript("test_vid", languages=["en"])
        assert result == "hello world"
        assert instance.fetch.call_count == 1


def test_get_transcript_retries_with_backoff():
    """Fails 2x, succeeds 3rd. Verify time.sleep called with backoff delays."""
    from src.extractors.youtube import get_transcript

    mock_snippet = MagicMock()
    mock_snippet.text = "success"

    with (
        patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi,
        patch("src.extractors.youtube.time.sleep") as mock_sleep,
    ):
        instance = MockApi.return_value
        instance.fetch.side_effect = [
            Exception("fail1"),
            Exception("fail2"),
            [mock_snippet],
        ]

        result = get_transcript("test_vid", languages=["en"])
        assert result == "success"
        assert instance.fetch.call_count == 3
        # Backoff: sleep(1) after 1st fail, sleep(2) after 2nd fail
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)


def test_get_transcript_none_after_all_retries():
    """All 3 attempts fail → returns None."""
    from src.extractors.youtube import get_transcript

    with (
        patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi,
        patch("src.extractors.youtube.time.sleep"),
    ):
        instance = MockApi.return_value
        instance.fetch.side_effect = Exception("always fails")

        result = get_transcript("test_vid", languages=["en"])
        assert result is None
        assert instance.fetch.call_count == 3


def test_get_video_metadata_success():
    """oEmbed returns title + channel."""
    from src.extractors.youtube import get_video_metadata

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "title": "Test Video",
        "author_name": "TestChannel",
    }

    with patch("src.extractors.youtube.requests.get", return_value=mock_resp):
        meta = get_video_metadata("abc123")
        assert meta["title"] == "Test Video"
        assert meta["channel"] == "TestChannel"


def test_get_video_metadata_failure():
    """HTTP error → fallback dict with None values."""
    from src.extractors.youtube import get_video_metadata

    with patch("src.extractors.youtube.requests.get", side_effect=Exception("network")):
        meta = get_video_metadata("abc123")
        assert meta["title"] is None
        assert meta["channel"] is None
