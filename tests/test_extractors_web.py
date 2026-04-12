"""Tests for src.extractors.web — trafilatura-based article extraction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _meta(**kw):
    """Build a metadata-like object with attribute access."""
    defaults = {"title": "T", "author": "A", "date": "2025-06-15", "sitename": "example.com"}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_extract_web_article_success():
    from src.extractors.web import extract_web_article

    text = "x" * 500
    with (
        patch("src.extractors.web.trafilatura.fetch_url", return_value="<html>...</html>"),
        patch("src.extractors.web.trafilatura.extract", return_value=text),
        patch("src.extractors.web.trafilatura.extract_metadata", return_value=_meta()),
    ):
        result = extract_web_article("https://example.com/foo")

    assert result is not None
    assert result["title"] == "T"
    assert result["author"] == "A"
    assert result["date"] == "2025-06-15"
    assert result["text"] == text
    assert result["source_url"] == "https://example.com/foo"
    assert result["sitename"] == "example.com"


def test_extract_web_article_returns_none_on_fetch_failure():
    from src.extractors.web import extract_web_article

    with patch("src.extractors.web.trafilatura.fetch_url", return_value=None):
        assert extract_web_article("https://example.com/foo") is None


def test_extract_web_article_returns_none_on_short_text():
    from src.extractors.web import extract_web_article

    with (
        patch("src.extractors.web.trafilatura.fetch_url", return_value="<html>"),
        patch("src.extractors.web.trafilatura.extract", return_value="too short"),
        patch("src.extractors.web.trafilatura.extract_metadata", return_value=_meta()),
    ):
        assert extract_web_article("https://example.com/foo") is None


def test_extract_web_article_returns_none_on_empty_text():
    from src.extractors.web import extract_web_article

    with (
        patch("src.extractors.web.trafilatura.fetch_url", return_value="<html>"),
        patch("src.extractors.web.trafilatura.extract", return_value=None),
        patch("src.extractors.web.trafilatura.extract_metadata", return_value=_meta()),
    ):
        assert extract_web_article("https://example.com/foo") is None


def test_extract_web_article_handles_missing_metadata():
    """When metadata is None, falls back to URL/Unknown defaults."""
    from src.extractors.web import extract_web_article

    text = "x" * 500
    url = "https://example.com/missing"
    with (
        patch("src.extractors.web.trafilatura.fetch_url", return_value="<html>"),
        patch("src.extractors.web.trafilatura.extract", return_value=text),
        patch("src.extractors.web.trafilatura.extract_metadata", return_value=None),
    ):
        result = extract_web_article(url)

    assert result is not None
    assert result["title"] == url
    assert result["author"] == "Unknown"
    assert result["date"] is None
    assert result["sitename"] is None


def test_extract_web_article_returns_none_on_exception():
    from src.extractors.web import extract_web_article

    with patch("src.extractors.web.trafilatura.fetch_url", side_effect=RuntimeError("net")):
        assert extract_web_article("https://example.com/foo") is None


def test_extract_web_article_strips_comments_and_keeps_tables():
    """The extract() call must request comment-free, table-included plain text."""
    from src.extractors.web import extract_web_article

    text = "x" * 500
    with (
        patch("src.extractors.web.trafilatura.fetch_url", return_value="<html>"),
        patch("src.extractors.web.trafilatura.extract", return_value=text) as mock_extract,
        patch("src.extractors.web.trafilatura.extract_metadata", return_value=_meta()),
    ):
        extract_web_article("https://example.com/foo")

    _, kwargs = mock_extract.call_args
    assert kwargs["include_comments"] is False
    assert kwargs["include_tables"] is True
    assert kwargs["output_format"] == "txt"
