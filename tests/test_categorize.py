"""Tests for src.categorize — slug validation, LLM fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_categories(tmp_path, monkeypatch):
    """Isolate categories file."""
    import src.config
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(src.config, "DATA_DIR", data)
    monkeypatch.setattr(src.config, "CATEGORIES_FILE", data / "categories.yml")


def _mock_llm_response(text: str):
    """Build a mock OpenAI client returning given text."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    client = MagicMock()
    client.chat.completions.create.return_value = mock_response
    return client


def test_categorize_returns_existing_category():
    """Known slug returned by LLM → (slug, False)."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("ai-agents")):
        slug, is_new = categorize_content("AI Agents Tutorial", "content here")
        assert slug == "ai-agents"
        assert is_new is False


def test_categorize_returns_new_valid_slug():
    """Unknown but valid slug → (slug, True)."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("machine-learning")):
        slug, is_new = categorize_content("ML Tutorial", "content")
        assert slug == "machine-learning"
        assert is_new is True


def test_categorize_rejects_long_slug():
    """Slug > 30 chars → fallback to ai-news."""
    from src.categorize import categorize_content

    long_slug = "a" * 50
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response(long_slug)):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_rejects_non_alnum_slug():
    """Slug with special chars → fallback."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("cat/../hack")):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_fallback_on_api_error():
    """API exception → ('ai-news', False)."""
    from src.categorize import categorize_content

    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False
